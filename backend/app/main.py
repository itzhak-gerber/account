"""FastAPI application: REST API at /api/v1, browser login at /auth, MCP server at /mcp."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.transport_security import TransportSecuritySettings

from app.api.v1 import router as api_v1_router
from app.auth.routes import router as auth_router
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.mcp.server import build_mcp_server


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    mcp = build_mcp_server()
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=settings.mcp_allowed_origins,
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # A mounted app's own lifespan is not run, so start the MCP session manager here.
        async with mcp.session_manager.run():
            yield
        await get_engine().dispose()

    app = FastAPI(
        title="Invoice Platform API",
        version=settings.version,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(api_v1_router)
    # OAuth Protected Resource Metadata (RFC 9728) for the MCP endpoint lives at the site root:
    # /.well-known/oauth-protected-resource/mcp. MCP clients discover Keycloak from it.
    app.router.routes.extend(
        create_protected_resource_routes(
            resource_url=settings.mcp_resource_url,  # type: ignore[arg-type]
            authorization_servers=[settings.oidc_issuer],  # type: ignore[list-item]
            resource_name="Invoice Platform",
        )
    )
    app.mount("/mcp", mcp_app)
    return app


app = create_app()
