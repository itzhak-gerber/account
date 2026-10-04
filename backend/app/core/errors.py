"""Application errors returned as {"error": {"code", "message"}}. The UI maps codes to Hebrew."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str = "", *, code: str | None = None, **details: Any) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        if code:
            self.code = code
        self.details = details


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class MfaRequired(Forbidden):
    code = "mfa_required"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse({"error": body}, status_code=exc.status_code)
