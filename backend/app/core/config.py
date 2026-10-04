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

    database_url: str = "postgresql+asyncpg://invoice:invoice@localhost:5432/invoice"
    redis_url: str = "redis://localhost:6379/0"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
