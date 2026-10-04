"""A fake Keycloak: discovery, JWKS and token endpoints served through httpx.MockTransport."""

import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.oidc import OidcClient
from app.core.config import Settings


@dataclass
class FakeUser:
    email: str
    name: str = "Test User"
    sub: str = field(default_factory=lambda: str(uuid.uuid4()))
    email_verified: bool = True


class FakeIdP:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.issuer = settings.oidc_issuer
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = "test-key"
        self._codes: dict[str, dict[str, Any]] = {}
        self._refresh: dict[str, dict[str, Any]] = {}
        self.refresh_fails = False

    # --- token minting -------------------------------------------------------------------

    def _sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self._kid})

    def _base(self, user: FakeUser, aud: str, amr: list[str]) -> dict[str, Any]:
        now = int(time.time())
        return {
            "iss": self.issuer,
            "sub": user.sub,
            "aud": aud,
            "iat": now,
            "exp": now + 300,
            "email": user.email,
            "email_verified": user.email_verified,
            "name": user.name,
            "amr": amr,
            "azp": self.settings.oidc_client_id,
            "scope": "openid email profile",
        }

    def access_token(
        self, user: FakeUser, *, mfa: bool = False, aud: str | None = None, **extra: Any
    ) -> str:
        claims = self._base(
            user, aud or self.settings.oidc_audience, ["pwd", "otp"] if mfa else ["pwd"]
        )
        claims.update(extra)
        return self._sign(claims)

    def issue_code(self, user: FakeUser, *, nonce: str, mfa: bool = False) -> str:
        code = secrets.token_urlsafe(16)
        self._codes[code] = {"user": user, "nonce": nonce, "mfa": mfa}
        return code

    # --- HTTP endpoints ------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        base = "/realms/invoice/protocol/openid-connect"
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": self.issuer,
                    "authorization_endpoint": f"{self.issuer}/protocol/openid-connect/auth",
                    "token_endpoint": f"{self.issuer}/protocol/openid-connect/token",
                    "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
                    "end_session_endpoint": f"{self.issuer}/protocol/openid-connect/logout",
                },
            )
        if path == f"{base}/certs":
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
            jwk.update({"kid": self._kid, "use": "sig", "alg": "RS256"})
            return httpx.Response(200, json={"keys": [jwk]})
        if path == f"{base}/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form["grant_type"] == "authorization_code":
                entry = self._codes.pop(form["code"], None)
                if entry is None:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return self._tokens(entry["user"], entry["mfa"], nonce=entry["nonce"])
            if form["grant_type"] == "refresh_token":
                entry = self._refresh.get(form["refresh_token"])
                if entry is None or self.refresh_fails:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return self._tokens(entry["user"], entry["mfa"], nonce=None)
        return httpx.Response(404)

    def _tokens(self, user: FakeUser, mfa: bool, *, nonce: str | None) -> httpx.Response:
        id_claims = self._base(
            user, self.settings.oidc_client_id, ["pwd", "otp"] if mfa else ["pwd"]
        )
        if nonce:
            id_claims["nonce"] = nonce
        refresh = secrets.token_urlsafe(16)
        self._refresh[refresh] = {"user": user, "mfa": mfa}
        return httpx.Response(
            200,
            json={
                "access_token": self.access_token(user, mfa=mfa),
                "id_token": self._sign(id_claims),
                "refresh_token": refresh,
                "expires_in": 300,
            },
        )

    def client(self) -> OidcClient:
        return OidcClient(
            self.settings, httpx.AsyncClient(transport=httpx.MockTransport(self._handle))
        )
