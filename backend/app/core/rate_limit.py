"""Fixed-window rate limiting per client IP, stored in Redis.

If Redis is unavailable the request is allowed (logged), so an outage of the cache does not
take the whole app down.
"""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.redis import get_redis

log = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        settings = get_settings()
        if path.startswith("/auth/"):
            bucket, limit = "auth", settings.rate_limit_auth_per_minute
        elif path.startswith(("/api/", "/mcp")):
            bucket, limit = "api", settings.rate_limit_api_per_minute
        else:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"ratelimit:{bucket}:{ip}:{window}"
        try:
            redis = get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 70)
        except Exception as exc:
            log.warning("rate_limit.unavailable", error=str(exc))
            return await call_next(request)
        if count > limit:
            return JSONResponse(
                {"error": {"code": "rate_limited", "message": "Too many requests"}},
                status_code=429,
                headers={"Retry-After": str(60 - int(time.time()) % 60)},
            )
        return await call_next(request)
