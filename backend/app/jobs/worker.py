"""Background worker (arq). Run with: ``arq app.jobs.worker.WorkerSettings``."""

from email.message import EmailMessage
from typing import Any, ClassVar

import aiosmtplib
import structlog
from arq.connections import RedisSettings

from app.core.config import get_settings

log = structlog.get_logger()


async def ping(ctx: dict[str, Any]) -> str:
    log.info("worker.ping")
    return "pong"


async def send_email(ctx: dict[str, Any], *, to: str, subject: str, html: str, text: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
    )
    log.info("email.sent", subject=subject)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, send_email]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 5
