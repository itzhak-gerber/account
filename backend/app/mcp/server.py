"""MCP server. Tools are thin adapters over the service layer, exactly like REST routers.

Authentication: OAuth 2.1 bearer tokens from Keycloak (audience ``invoice-api``). Each tool
call resolves the same Principal and BusinessContext as the REST API, so roles, two-factor
rules and row-level security apply identically. Membership management stays web-only.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import get_oidc_client
from app.auth.principal import Principal, enter_business, principal_from_bearer
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import AppError, NotAuthenticated
from app.models import Role, User
from app.schemas.identity import BusinessOut, MemberOut, UserOut
from app.services import businesses
from app.services.system import SystemStatus, get_system_status


class KeycloakTokenVerifier:
    """Validates bearer tokens for the MCP endpoint (signature, issuer, audience, expiry)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        settings = get_settings()
        try:
            claims = await get_oidc_client().validate(token, audience=settings.oidc_audience)
        except NotAuthenticated:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp", "")),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
        )


@asynccontextmanager
async def _principal_session() -> AsyncIterator[tuple[AsyncSession, Principal]]:
    access = get_access_token()
    if access is None:
        raise PermissionError("Not authenticated")
    async with get_sessionmaker()() as session:
        try:
            principal = await principal_from_bearer(
                session, get_oidc_client(), access.token, channel="mcp"
            )
            yield session, principal
            await session.commit()
        except AppError as exc:
            # Business errors (permission, not found, 2FA) are shown to the client as-is.
            raise ToolError(f"{exc.code}: {exc.message}") from exc


class BusinessSummary(BaseModel):
    business: BusinessOut
    role: Role


class WhoAmI(BaseModel):
    user: UserOut
    mfa: bool


def build_mcp_server(*, with_auth: bool = True) -> MCPServer:
    settings = get_settings()
    auth_kwargs: dict[str, object] = {}
    if with_auth:
        auth_kwargs = {
            "token_verifier": KeycloakTokenVerifier(),
            "auth": AuthSettings(
                issuer_url=settings.oidc_issuer,
                resource_server_url=settings.mcp_resource_url,
                validate_token_resource=False,  # the verifier checks the audience itself
            ),
        }
    mcp = MCPServer(
        name="invoice-platform",
        version=settings.version,
        instructions=(
            "Invoice platform for Israeli businesses: customers, items, quotes, invoices, "
            "receipts and credit notes. Every business-scoped tool takes a business_id; call "
            "list_businesses first. Documents are created as drafts; issuing is irreversible."
        ),
        **auth_kwargs,  # type: ignore[arg-type]
    )

    @mcp.tool(name="get_system_status")
    async def get_system_status_tool() -> SystemStatus:
        """Return the platform status (version, environment, database health)."""
        async with get_sessionmaker()() as session:
            return await get_system_status(session)

    @mcp.tool()
    async def whoami() -> WhoAmI:
        """Return the signed-in user and whether they signed in with two-factor authentication."""
        async with _principal_session() as (session, principal):
            user = await session.get(User, principal.user_id)
            return WhoAmI(user=UserOut.model_validate(user), mfa=principal.mfa)

    @mcp.tool()
    async def list_businesses() -> list[BusinessSummary]:
        """List the businesses the signed-in user belongs to, with their role in each."""
        async with _principal_session() as (session, principal):
            rows = await businesses.list_for_user(session, principal)
            return [
                BusinessSummary(business=BusinessOut.model_validate(b), role=r) for b, r in rows
            ]

    @mcp.tool()
    async def get_business(business_id: uuid.UUID) -> BusinessOut:
        """Get a business's details (name, tax ID, type, address, contact)."""
        async with _principal_session() as (session, principal):
            ctx = await enter_business(session, principal, business_id)
            return BusinessOut.model_validate(await businesses.get_business(session, ctx))

    @mcp.tool()
    async def list_members(business_id: uuid.UUID) -> list[MemberOut]:
        """List the members of a business and their roles."""
        async with _principal_session() as (session, principal):
            ctx = await enter_business(session, principal, business_id)
            return await businesses.list_members(session, ctx)

    return mcp
