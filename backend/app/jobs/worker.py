"""Background worker (arq). Run with: ``arq app.jobs.worker.WorkerSettings``."""

from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings

from app.core.config import get_settings

log = structlog.get_logger()


async def ping(ctx: dict[str, Any]) -> str:
    log.info("worker.ping")
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
