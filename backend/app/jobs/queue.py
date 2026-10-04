"""Enqueue background jobs (run by the arq worker)."""

from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def enqueue(function: str, **kwargs: Any) -> None:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await _pool.enqueue_job(function, **kwargs)
