"""Who is calling: a browser session (cookie) or an API/MCP client (bearer token)."""

import time
import uuid
from dataclasses import dataclass, replace
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import OidcClient, OidcError, get_oidc_client
from app.auth.sessions import SessionStore
from app.core.config import Settings, get_settings
from app.core.db import get_session, set_rls_context
from app.core.errors import Forbidden, MfaRequired, NotAuthenticated, NotFound
from app.core.redis import get_redis
from app.models import BusinessMember, Role, User
from app.services.permissions import MFA_REQUIRED_ROLES
from app.services.users import upsert_from_claims

Channel = Literal["web", "api", "mcp"]
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"
# Authentication-method references that count as a second factor.
MFA_AMR_VALUES = frozenset({"otp", "mfa", "hwk", "swk"})


def session_cookie_name(settings: Settings) -> str:
    # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and Path=/.
    return "__Host-session" if settings.secure_cookies else "session"


def claims_have_mfa(claims: dict[str, object]) -> bool:
    amr = claims.get("amr") or []
    return isinstance(amr, list) and any(v in MFA_AMR_VALUES for v in amr)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    channel: Channel
    mfa: bool
    ip: str | None = None
    user_agent: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class BusinessContext:
    principal: Principal
    business_id: uuid.UUID
    role: Role


def get_session_store() -> SessionStore:
    return SessionStore(get_redis(), get_settings())


async def principal_from_bearer(
    session: AsyncSession, oidc: OidcClient, token: str, *, channel: Channel, ip: str | None = None
) -> Principal:
    claims = await oidc.validate(token, audience=get_settings().oidc_audience)
    user = await upsert_from_claims(session, claims)
    await set_rls_context(session, user_id=user.id)
    return Principal(
        user_id=user.id, email=user.email, channel=channel, mfa=claims_have_mfa(claims), ip=ip
    )


async def get_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    oidc: Annotated[OidcClient, Depends(get_oidc_client)],
) -> Principal:
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        principal = await principal_from_bearer(
            session, oidc, authorization[7:].strip(), channel="api", ip=ip
        )
        return replace(principal, user_agent=user_agent)

    settings = get_settings()
    session_id = request.cookies.get(session_cookie_name(settings))
    if not session_id:
        raise NotAuthenticated()
    data = await store.get(session_id)
    if data is None:
        raise NotAuthenticated("Session expired", code="session_expired")

    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != data.csrf_token:
        raise Forbidden("Missing or invalid CSRF token", code="csrf_failed")

    if time.time() >= data.access_expires_at:
        # Re-check with Keycloak periodically so disabled users and ended sessions take effect.
        if not data.refresh_token:
            await store.delete(session_id, data.user_id)
            raise NotAuthenticated("Session expired", code="session_expired")
        try:
            tokens = await oidc.refresh(data.refresh_token)
        except OidcError:
            await store.delete(session_id, data.user_id)
            raise NotAuthenticated("Session expired", code="session_expired") from None
        data.refresh_token = tokens.refresh_token or data.refresh_token
        data.id_token = tokens.id_token or data.id_token
        data.access_expires_at = time.time() + tokens.expires_in
    await store.save(session_id, data)

    user = await session.get(User, uuid.UUID(data.user_id))
    if user is None or not user.is_active:
        await store.delete(session_id, data.user_id)
        raise NotAuthenticated("Account unavailable", code="account_disabled")
    await set_rls_context(session, user_id=user.id)
    return Principal(
        user_id=user.id,
        email=user.email,
        channel="web",
        mfa=data.mfa,
        ip=ip,
        user_agent=user_agent,
        session_id=session_id,
    )


async def enter_business(
    session: AsyncSession, principal: Principal, business_id: uuid.UUID
) -> BusinessContext:
    """Check membership, set the RLS business context, and enforce MFA for privileged roles."""
    member = await session.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id, BusinessMember.user_id == principal.user_id
        )
    )
    if member is None:
        # Same answer whether the business does not exist or belongs to someone else.
        raise NotFound("Business not found", code="business_not_found")
    role = Role(member.role)
    if role in MFA_REQUIRED_ROLES and get_settings().require_mfa_for_admins and not principal.mfa:
        raise MfaRequired("Two-factor authentication is required for this role")
    await set_rls_context(session, business_id=business_id)
    return BusinessContext(principal=principal, business_id=business_id, role=role)


async def get_business_context(
    business_id: uuid.UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BusinessContext:
    return await enter_business(session, principal, business_id)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
CurrentBusiness = Annotated[BusinessContext, Depends(get_business_context)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
