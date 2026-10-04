"""System status. Like every service, it is shared by the REST API and the MCP server."""

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


class SystemStatus(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]


async def get_system_status(session: AsyncSession) -> SystemStatus:
    settings = get_settings()
    try:
        await session.execute(text("SELECT 1"))
        database: Literal["ok", "unavailable"] = "ok"
    except Exception:
        database = "unavailable"
    return SystemStatus(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        environment=settings.environment,
        database=database,
    )
