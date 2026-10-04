"""Baseline security headers on every response."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

# API responses never render HTML, so they get the strictest policy. The interactive
# API docs (disabled in production) load scripts from a CDN and are left without one.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_DOCS_PATH = "/api/docs"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, hsts: bool) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(_DOCS_PATH):
            response.headers.setdefault("Content-Security-Policy", _API_CSP)
        if self._hsts:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
