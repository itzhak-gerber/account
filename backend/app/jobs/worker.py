"""Background worker (arq). Run with: ``arq app.jobs.worker.WorkerSettings``."""

import base64
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, ClassVar

import aiosmtplib
import structlog
from arq import Retry
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import get_sessionmaker, set_rls_context
from app.models import DeliveryStatus, DocumentDelivery

log = structlog.get_logger()
MAX_TRIES = 5


async def ping(ctx: dict[str, Any]) -> str:
    log.info("worker.ping")
    return "pong"


async def _smtp_send(message: EmailMessage) -> None:
    settings = get_settings()
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
    )


def _message(to: list[str] | str, subject: str, text: str, html: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = get_settings().email_from
    message["To"] = ", ".join(to) if isinstance(to, list) else to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


async def send_email(ctx: dict[str, Any], *, to: str, subject: str, html: str, text: str) -> None:
    await _smtp_send(_message(to, subject, text, html))
    log.info("email.sent", subject=subject)


async def _record(business_id: str, delivery_id: str, **values: Any) -> None:
    async with get_sessionmaker()() as session:
        await set_rls_context(session, business_id=uuid.UUID(business_id))
        delivery = await session.get(DocumentDelivery, uuid.UUID(delivery_id))
        if delivery is not None:
            for key, value in values.items():
                setattr(delivery, key, value)
            await session.commit()


async def send_document_email(
    ctx: dict[str, Any],
    *,
    delivery_id: str,
    business_id: str,
    to: list[str],
    subject: str,
    html: str,
    text: str,
    attachment_name: str,
    attachment_b64: str,
    logo_b64: str | None,
    logo_cid: str,
) -> None:
    """Send a document to a customer; record sent/failed on its delivery row (retried)."""
    message = _message(to, subject, text, html)
    if logo_b64:
        # Inline image referenced by the HTML as cid:<logo_cid>.
        html_part = message.get_body(preferencelist=("html",))
        assert html_part is not None
        html_part.add_related(
            base64.b64decode(logo_b64), maintype="image", subtype="png", cid=f"<{logo_cid}>"
        )
    message.add_attachment(
        base64.b64decode(attachment_b64),
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )
    attempt = int(ctx.get("job_try", 1))
    try:
        await _smtp_send(message)
    except Exception as exc:
        log.warning(
            "document_email.failed", delivery_id=delivery_id, attempt=attempt, error=str(exc)
        )
        await _record(
            business_id,
            delivery_id,
            status=DeliveryStatus.FAILED,
            error=str(exc)[:500],
            attempts=attempt,
        )
        if attempt < MAX_TRIES:
            raise Retry(defer=30 * attempt) from exc
        return
    await _record(
        business_id,
        delivery_id,
        status=DeliveryStatus.SENT,
        error=None,
        attempts=attempt,
        sent_at=datetime.now(UTC),
    )
    log.info("document_email.sent", delivery_id=delivery_id)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, send_email, send_document_email]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES
