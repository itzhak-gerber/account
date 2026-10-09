"""Application settings, loaded from environment variables (prefix ``APP_``)."""

from functools import lru_cache
from typing import Literal
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


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
    # In the cloud the passwords come from Key Vault as separate secrets and are put into the
    # URLs above, so no connection string with a password sits in plain configuration.
    database_password: str | None = None
    redis_password: str | None = None

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

    # Signs short-lived download links (e.g. PDFs for MCP clients). Must be set in production.
    secret_key: str = "dev-only-secret-key-change-me"  # noqa: S105
    # Generated files (PDFs, logos): a local folder, or Azure Blob Storage in the cloud.
    storage_backend: Literal["local", "azure"] = "local"
    storage_dir: str = "var/files"
    azure_storage_account_url: str | None = None  # https://<account>.blob.core.windows.net
    azure_storage_container: str = "files"
    # Only for local tests against the Azurite emulator; the cloud uses a managed identity.
    azure_storage_connection_string: str | None = None
    # The user-assigned managed identity's client id (also used by Azure SDKs).
    azure_client_id: str | None = None
    timezone: str = "Asia/Jerusalem"
    # Israel Tax Authority allocation numbers: off until the software is registered.
    ita_allocation_enabled: bool = False

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    email_from: str = "חשבוניות <noreply@invoice.local>"

    # Web Push (VAPID). The private key is base64url DER (EC P-256); empty disables push.
    vapid_private_key: str = ""
    # Contact for push services (mailto: or https URL); defaults to the public URL.
    vapid_subject: str = ""

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

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        if self.environment == "production" and self.secret_key.startswith("dev-only"):
            raise ValueError("APP_SECRET_KEY must be set in production")
        return self

    @model_validator(mode="after")
    def _insert_passwords(self) -> "Settings":
        if self.database_password:
            url = make_url(self.database_url).set(password=self.database_password)
            self.database_url = url.render_as_string(hide_password=False)
        if self.redis_password:
            parts = urlsplit(self.redis_url)
            host = parts.netloc.rsplit("@", 1)[-1]
            user = parts.username or ""
            netloc = f"{quote(user, safe='')}:{quote(self.redis_password, safe='')}@{host}"
            self.redis_url = urlunsplit(parts._replace(netloc=netloc))
        return self

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
