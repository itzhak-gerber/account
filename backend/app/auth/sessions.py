# mypy: disable-error-code="misc"
# (redis-py types set commands as "Awaitable[T] | T" even on the asyncio client.)
"""Server-side browser sessions in Redis.

The browser only holds a random session id in an httpOnly cookie. Keycloak tokens never
reach the browser. Redis keys use a SHA-256 of the id, so a Redis dump cannot be replayed
as cookies.
"""

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, field

from redis.asyncio import Redis

from app.core.config import Settings


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class SessionData:
    user_id: str
    subject: str
    mfa: bool
    csrf_token: str
    refresh_token: str | None
    id_token: str | None
    access_expires_at: float
    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    user_agent: str = ""
    ip: str = ""


class SessionStore:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._idle = settings.session_idle_minutes * 60
        self._max = settings.session_max_hours * 3600

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session:{_hash(session_id)}"

    @staticmethod
    def _user_key(user_id: str) -> str:
        return f"user_sessions:{user_id}"

    async def create(self, data: SessionData) -> str:
        session_id = secrets.token_urlsafe(32)
        key = self._key(session_id)
        await self._redis.set(key, json.dumps(asdict(data)), ex=self._idle)
        await self._redis.sadd(self._user_key(data.user_id), key)
        await self._redis.expire(self._user_key(data.user_id), self._max)
        return session_id

    async def get(self, session_id: str) -> SessionData | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        data = SessionData(**json.loads(raw))
        now = time.time()
        if now - data.created_at > self._max:
            await self.delete(session_id, data.user_id)
            return None
        return data

    async def save(self, session_id: str, data: SessionData) -> None:
        """Persist changes and slide the idle timeout (never past the absolute lifetime)."""
        data.last_seen_at = time.time()
        remaining = int(self._max - (data.last_seen_at - data.created_at))
        await self._redis.set(
            self._key(session_id), json.dumps(asdict(data)), ex=max(1, min(self._idle, remaining))
        )

    async def delete(self, session_id: str, user_id: str) -> None:
        key = self._key(session_id)
        await self._redis.delete(key)
        await self._redis.srem(self._user_key(user_id), key)

    async def delete_all_for_user(self, user_id: uuid.UUID | str) -> int:
        user_key = self._user_key(str(user_id))
        keys = await self._redis.smembers(user_key)
        if keys:
            await self._redis.delete(*keys)
        await self._redis.delete(user_key)
        return len(keys)

    async def count_for_user(self, user_id: uuid.UUID | str) -> int:
        user_key = self._user_key(str(user_id))
        alive = 0
        for key in await self._redis.smembers(user_key):
            if await self._redis.exists(key):
                alive += 1
            else:
                await self._redis.srem(user_key, key)
        return alive
