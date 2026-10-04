"""Browser login flow (Backend-for-Frontend): Authorization Code + PKCE with Keycloak.

The backend does the OAuth exchange, keeps tokens server-side, and gives the browser an
httpOnly session cookie. State and PKCE verifier are bound to the browser by a short-lived
cookie, so a login started in one browser cannot be completed in another.
"""

import base64
import hashlib
import json
import secrets
import time
from typing import Annotated, Literal
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.auth.oidc import OidcClient, OidcError, get_oidc_client
from app.auth.principal import (
    CurrentPrincipal,
    DbSession,
    Principal,
    claims_have_mfa,
    get_session_store,
    session_cookie_name,
)
from app.auth.sessions import SessionData, SessionStore
from app.core.config import get_settings
from app.core.db import commit, set_rls_context
from app.core.errors import NotAuthenticated
from app.core.redis import get_redis
from app.services import audit
from app.services.users import upsert_from_claims

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_COOKIE = "login_state"
_LOGIN_TTL_SECONDS = 600
KcAction = Literal["UPDATE_PASSWORD", "CONFIGURE_TOTP"]


def _safe_return_to(value: str | None) -> str:
    # Only same-site relative paths; blocks open redirects such as //evil.example.
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def _redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/auth/callback"


def _cookie_args() -> dict[str, object]:
    return {
        "httponly": True,
        "secure": get_settings().secure_cookies,
        "samesite": "lax",
        "path": "/",
    }


@router.get("/login")
async def login(
    oidc: Annotated[OidcClient, Depends(get_oidc_client)],
    return_to: str | None = None,
    register: bool = False,
    action: KcAction | None = None,
    reauth: bool = False,
) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    await get_redis().set(
        f"oidc_login:{state}",
        json.dumps(
            {
                "verifier": verifier,
                "nonce": nonce,
                "return_to": _safe_return_to(return_to),
                "action": action,
            }
        ),
        ex=_LOGIN_TTL_SECONDS,
    )
    url = await oidc.authorization_url(
        state=state,
        nonce=nonce,
        code_challenge=challenge.decode(),
        redirect_uri=_redirect_uri(),
        register=register,
        kc_action=action,
        force_login=reauth,
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(_LOGIN_COOKIE, state, max_age=_LOGIN_TTL_SECONDS, **_cookie_args())  # type: ignore[arg-type]
    return response


def _back_to_app(path: str, error: str | None = None) -> RedirectResponse:
    if error:
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}{urlencode({'auth_error': error})}"
    response = RedirectResponse(path, status_code=302)
    response.delete_cookie(_LOGIN_COOKIE, path="/")
    return response


@router.get("/callback")
async def callback(
    request: Request,
    session: DbSession,
    store: Annotated[SessionStore, Depends(get_session_store)],
    oidc: Annotated[OidcClient, Depends(get_oidc_client)],
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> Response:
    if not state or request.cookies.get(_LOGIN_COOKIE) != state:
        return _back_to_app("/", "login_state_mismatch")
    raw = await get_redis().getdel(f"oidc_login:{state}")
    if raw is None:
        return _back_to_app("/", "login_expired")
    pending = json.loads(raw)
    return_to = pending["return_to"]
    if error or not code:
        # e.g. the user cancelled setting up two-factor authentication.
        return _back_to_app(return_to, error or "login_failed")

    try:
        tokens = await oidc.exchange_code(
            code=code, code_verifier=pending["verifier"], redirect_uri=_redirect_uri()
        )
        settings = get_settings()
        id_claims = await oidc.validate(
            tokens.id_token or "", audience=settings.oidc_client_id, nonce=pending["nonce"]
        )
        access_claims = await oidc.validate(tokens.access_token, audience=settings.oidc_audience)
    except (OidcError, NotAuthenticated) as exc:
        log.warning("auth.callback_failed", reason=str(exc))
        return _back_to_app(return_to, "login_failed")
    if access_claims["sub"] != id_claims["sub"]:
        return _back_to_app(return_to, "login_failed")

    mfa = claims_have_mfa(access_claims)
    if pending.get("action") == "CONFIGURE_TOTP" and not mfa:
        # Setting up the authenticator does not itself count as using it; sign in once more
        # (password + code) so this session is recorded as two-factor.
        response = RedirectResponse(
            f"/auth/login?{urlencode({'return_to': return_to, 'reauth': 'true'})}", status_code=302
        )
        response.delete_cookie(_LOGIN_COOKIE, path="/")
        return response

    user = await upsert_from_claims(session, id_claims, record_login=True)
    await set_rls_context(session, user_id=user.id)
    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")[:500]
    session_id = await store.create(
        SessionData(
            user_id=str(user.id),
            subject=user.idp_subject,
            mfa=mfa,
            csrf_token=secrets.token_urlsafe(32),
            refresh_token=tokens.refresh_token,
            id_token=tokens.id_token,
            access_expires_at=time.time() + tokens.expires_in,
            user_agent=user_agent,
            ip=ip,
        )
    )
    await audit.record(
        session,
        Principal(
            user_id=user.id,
            email=user.email,
            channel="web",
            mfa=mfa,
            ip=ip or None,
            user_agent=user_agent,
        ),
        action="user.login",
        entity_type="user",
        entity_id=user.id,
        business_id=None,
        changes={"mfa": mfa},
    )
    await commit(session)

    response = _back_to_app(return_to)
    response.set_cookie(
        session_cookie_name(get_settings()),
        session_id,
        max_age=get_settings().session_max_hours * 3600,
        **_cookie_args(),  # type: ignore[arg-type]
    )
    return response


async def _end_session(principal: CurrentPrincipal, store: SessionStore) -> str | None:
    id_token = None
    if principal.session_id:
        data = await store.get(principal.session_id)
        id_token = data.id_token if data else None
        await store.delete(principal.session_id, str(principal.user_id))
    return id_token


@router.post("/logout")
async def logout(
    principal: CurrentPrincipal,
    store: Annotated[SessionStore, Depends(get_session_store)],
    oidc: Annotated[OidcClient, Depends(get_oidc_client)],
) -> JSONResponse:
    id_token = await _end_session(principal, store)
    # The browser then visits Keycloak to end the single-sign-on session too.
    logout_url = await oidc.end_session_url(
        id_token_hint=id_token, post_logout_redirect=f"{get_settings().public_url.rstrip('/')}/"
    )
    response = JSONResponse({"logout_url": logout_url})
    response.delete_cookie(session_cookie_name(get_settings()), path="/")
    return response


@router.post("/logout-all")
async def logout_all(
    principal: CurrentPrincipal,
    session: DbSession,
    store: Annotated[SessionStore, Depends(get_session_store)],
    oidc: Annotated[OidcClient, Depends(get_oidc_client)],
) -> JSONResponse:
    id_token = None
    if principal.session_id:
        data = await store.get(principal.session_id)
        id_token = data.id_token if data else None
    ended = await store.delete_all_for_user(principal.user_id)
    await audit.record(
        session,
        principal,
        action="user.logout_all",
        entity_type="user",
        entity_id=principal.user_id,
        business_id=None,
        changes={"sessions_ended": ended},
    )
    await commit(session)
    logout_url = await oidc.end_session_url(
        id_token_hint=id_token, post_logout_redirect=f"{get_settings().public_url.rstrip('/')}/"
    )
    response = JSONResponse({"logout_url": logout_url, "sessions_ended": ended})
    response.delete_cookie(session_cookie_name(get_settings()), path="/")
    return response
