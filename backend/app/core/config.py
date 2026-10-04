"""Application settings, loaded from environment variables (prefix ``APP_``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    environment: Literal["local", "test", "dev", "staging", "production"] = "local"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # Public URL of the web app (the browser's origin). Login redirects and cookies use it.
    public_url: str = "http://localhost:5173"

    # The app connects as a restricted role (not the schema owner) so row-level security applies.
    database_url: str = "postgresql+asyncpg://invoice_app:invoice_app@localhost:5432/invoice"
    redis_url: str = "redis://localhost:6379/0"

    # OpenID Connect (Keycloak). The issuer is the URL browsers see; the backend may reach
    # Keycloak on an internal address (e.g. inside docker-compose).
    oidc_issuer: str = "http://localhost:8080/realms/invoice"
    oidc_internal_url: str | None = None
    oidc_client_id: str = "invoice-web"
    oidc_client_secret: str = "dev-only-web-secret"  # noqa: S105 - overridden outside local dev
    oidc_audience: str = "invoice-api"

    # Browser sessions (stored server-side in Redis).
    session_idle_minutes: int = 30
    session_max_hours: int = 12

    # Owners and admins must sign in with two-factor authentication.
    require_mfa_for_admins: bool = True

    invitation_ttl_days: int = 7

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    email_from: str = "חשבוניות <noreply@invoice.local>"

    # Requests per minute per client IP.
    rate_limit_auth_per_minute: int = 30
    rate_limit_api_per_minute: int = 600

    # Host headers the MCP endpoint accepts (DNS-rebinding protection).
    mcp_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "localhost:*", "127.0.0.1:*", "backend:*"]
    )
    mcp_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:*", "http://127.0.0.1:*"]
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def oidc_backchannel_url(self) -> str:
        return self.oidc_internal_url or self.oidc_issuer

    @property
    def mcp_resource_url(self) -> str:
        return f"{self.public_url.rstrip('/')}/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
