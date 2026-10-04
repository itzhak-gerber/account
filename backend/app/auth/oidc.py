"""OpenID Connect client for Keycloak: login redirects, code exchange, token validation."""

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWK

from app.core.config import Settings, get_settings
from app.core.errors import NotAuthenticated

_JWKS_MIN_REFRESH_SECONDS = 30


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_in: int


class OidcError(Exception):
    pass


class OidcClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=10)
        self._discovery: dict[str, Any] | None = None
        self._jwks: dict[str, PyJWK] = {}
        self._jwks_fetched_at = 0.0

    @property
    def issuer(self) -> str:
        return self._settings.oidc_issuer

    async def discovery(self) -> dict[str, Any]:
        if self._discovery is None:
            url = f"{self._settings.oidc_backchannel_url}/.well-known/openid-configuration"
            response = await self._http.get(url)
            response.raise_for_status()
            self._discovery = response.json()
        return self._discovery

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
        register: bool = False,
        kc_action: str | None = None,
        force_login: bool = False,
    ) -> str:
        endpoint: str = (await self.discovery())["authorization_endpoint"]
        if register:
            # Keycloak's registration page accepts the same parameters as the login page.
            endpoint = endpoint.removesuffix("/auth") + "/registrations"
        params = {
            "client_id": self._settings.oidc_client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "ui_locales": "he",
        }
        if kc_action:
            params["kc_action"] = kc_action
        if force_login:
            params["prompt"] = "login"
        return f"{endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            }
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def _token_request(self, data: dict[str, str]) -> TokenSet:
        endpoint = (await self.discovery())["token_endpoint"]
        response = await self._http.post(
            endpoint,
            data=data,
            auth=(self._settings.oidc_client_id, self._settings.oidc_client_secret),
        )
        if response.status_code != 200:
            raise OidcError(f"token endpoint returned {response.status_code}")
        body = response.json()
        return TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            id_token=body.get("id_token"),
            expires_in=int(body.get("expires_in", 300)),
        )

    async def end_session_url(self, *, id_token_hint: str | None, post_logout_redirect: str) -> str:
        endpoint = (await self.discovery())["end_session_endpoint"]
        # The end-session endpoint is shown to the browser, so it must use the public issuer.
        endpoint = endpoint.replace(self._settings.oidc_backchannel_url, self.issuer)
        params = {
            "client_id": self._settings.oidc_client_id,
            "post_logout_redirect_uri": post_logout_redirect,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"

    async def _signing_key(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._jwks and time.monotonic() - self._jwks_fetched_at > (
            _JWKS_MIN_REFRESH_SECONDS if self._jwks else 0
        ):
            response = await self._http.get((await self.discovery())["jwks_uri"])
            response.raise_for_status()
            self._jwks = {
                k["kid"]: PyJWK(k)
                for k in response.json()["keys"]
                if k.get("use", "sig") == "sig" and "kid" in k
            }
            self._jwks_fetched_at = time.monotonic()
        if kid not in self._jwks:
            raise NotAuthenticated("unknown signing key")
        return self._jwks[kid]

    async def validate(
        self, token: str, *, audience: str, nonce: str | None = None
    ) -> dict[str, Any]:
        """Validate signature, issuer, audience and expiry; return the claims."""
        try:
            key = await self._signing_key(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["RS256", "PS256", "ES256"],
                audience=audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise NotAuthenticated("invalid token") from exc
        if nonce is not None and claims.get("nonce") != nonce:
            raise NotAuthenticated("nonce mismatch")
        return claims


_client: OidcClient | None = None


def get_oidc_client() -> OidcClient:
    global _client
    if _client is None:
        _client = OidcClient(get_settings())
    return _client


def set_oidc_client(client: OidcClient | None) -> None:
    """Replace the shared client (tests use a fake identity provider)."""
    global _client
    _client = client
