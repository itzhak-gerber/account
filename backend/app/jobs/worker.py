"""Background worker (arq). Run with: ``arq app.jobs.worker.WorkerSettings``."""

import base64
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import aiosmtplib
import structlog
from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from sqlalchemy import text, update

from app.core.config import get_settings
from app.core.db import commit, get_sessionmaker, set_rls_context
from app.models import (
    DataExport,
    DeliveryStatus,
    Document,
    DocumentDelivery,
    ExportStatus,
    OutboxEvent,
)
from app.services import events, exports, notifications, push
from app.services.documents import today

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


async def send_push(
    ctx: dict[str, Any], *, user_ids: list[str], title: str, link: str, tag: str
) -> int:
    """Push one message to every device of these users. Devices the push service reports as
    gone (404/410) are forgotten; other failures are logged and not retried (the message is
    also in the in-app inbox)."""
    async with get_sessionmaker()() as session:
        targets = (
            await session.execute(
                text("SELECT id, endpoint, p256dh, auth FROM push_targets(CAST(:users AS uuid[]))"),
                {"users": user_ids},
            )
        ).all()
        outcome = await push.send_to(list(targets), push.payload(title=title, link=link, tag=tag))
        for gone in outcome.gone or []:
            await session.execute(text("SELECT forget_push_subscription(:id)"), {"id": gone})
        await commit(session)
    log.info("push.sent", devices=outcome.sent, of=outcome.devices, gone=len(outcome.gone or []))
    return outcome.sent


async def build_export(ctx: dict[str, Any], *, export_id: str, business_id: str) -> str:
    """Build a full data export (see services/exports.py); a failure is recorded on the row."""
    async with get_sessionmaker()() as session:
        await set_rls_context(session, business_id=uuid.UUID(business_id))
        try:
            export = await exports.build(session, uuid.UUID(export_id))
            await commit(session)
            log.info("export.ready", export_id=export_id, documents=export.documents)
            return "ready"
        except Exception as exc:
            await session.rollback()
            log.exception("export.failed", export_id=export_id)
            failed = await session.get(DataExport, uuid.UUID(export_id))
            if failed is not None:
                failed.status = ExportStatus.FAILED
                failed.error = str(exc)[:500]
                failed.finished_at = datetime.now(UTC)
                await commit(session)
            return "failed"


async def _record(
    business_id: str, delivery_id: str, *, final_failure: bool = False, **values: Any
) -> None:
    async with get_sessionmaker()() as session:
        await set_rls_context(session, business_id=uuid.UUID(business_id))
        delivery = await session.get(DocumentDelivery, uuid.UUID(delivery_id))
        if delivery is None:
            return
        for key, value in values.items():
            setattr(delivery, key, value)
        if final_failure:
            document = await session.get(Document, delivery.document_id)
            assert document is not None
            events.emit(
                session,
                document.business_id,
                "document.email_failed",
                {
                    "delivery_id": str(delivery.id),
                    "document_id": str(document.id),
                    "type": document.type,
                    "number": document.number,
                    "to": list(delivery.recipients),
                    "created_by_user_id": str(delivery.created_by_user_id),
                },
            )
        await commit(session)


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
            final_failure=attempt >= MAX_TRIES,
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


# --- notifications ---------------------------------------------------------------------

DISPATCH_BATCH = 50
DISPATCH_LEASE_SECONDS = 300
DISPATCH_MAX_ATTEMPTS = 5


async def _dispatch_one(
    event_id: uuid.UUID, business_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> None:
    async with get_sessionmaker()() as session:
        await set_rls_context(session, business_id=business_id)
        message = await notifications.message_for(
            session, business_id, event_id, event_type, payload
        )
        delivered = 0
        if message is not None:
            delivered = await notifications.deliver(session, business_id, message)
        await session.execute(
            update(OutboxEvent).where(OutboxEvent.id == event_id).values(status="done")
        )
        await commit(session)
    log.info("outbox.dispatched", event_type=event_type, notified=delivered)


async def _mark_failed(event_id: uuid.UUID, business_id: uuid.UUID) -> None:
    async with get_sessionmaker()() as session:
        await set_rls_context(session, business_id=business_id)
        await session.execute(
            update(OutboxEvent).where(OutboxEvent.id == event_id).values(status="failed")
        )
        await session.commit()


async def dispatch_outbox(ctx: dict[str, Any]) -> int:
    """Turn pending domain events into notifications. Safe to run concurrently: events are
    leased by the database, so each is handled once (and retried if a worker dies)."""
    handled = 0
    while True:
        async with get_sessionmaker()() as session:
            claimed = (
                await session.execute(
                    text("SELECT * FROM claim_outbox_events(:n, :lease)"),
                    {"n": DISPATCH_BATCH, "lease": DISPATCH_LEASE_SECONDS},
                )
            ).all()
            await session.commit()
        for event_id, business_id, event_type, payload, attempts in claimed:
            try:
                await _dispatch_one(event_id, business_id, event_type, payload)
            except Exception:
                log.exception("outbox.dispatch_failed", event_id=str(event_id), attempts=attempts)
                if attempts >= DISPATCH_MAX_ATTEMPTS:
                    await _mark_failed(event_id, business_id)
            handled += 1
        if len(claimed) < DISPATCH_BATCH:
            return handled


async def raise_overdue_events(ctx: dict[str, Any]) -> int:
    """Daily: one event per invoice that became overdue in the last week (once each)."""
    yesterday = today() - timedelta(days=1)
    async with get_sessionmaker()() as session:
        count = await session.scalar(
            text("SELECT enqueue_overdue_events(:since, :until)"),
            {"since": yesterday - timedelta(days=6), "until": yesterday},
        )
        await session.execute(text("SELECT purge_old_notifications()"))
        await session.commit()
    log.info("overdue.raised", count=count)
    if count:
        await dispatch_outbox(ctx)
    return int(count or 0)


async def raise_daily_summaries(ctx: dict[str, Any]) -> int:
    """Every morning: one summary of yesterday per business that has issued documents."""
    async with get_sessionmaker()() as session:
        count = await session.scalar(
            text("SELECT enqueue_daily_summaries(:day)"),
            {"day": today() - timedelta(days=1)},
        )
        await session.commit()
    log.info("daily_summaries.raised", count=count)
    if count:
        await dispatch_outbox(ctx)
    return int(count or 0)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        send_email,
        send_document_email,
        func(send_push, max_tries=1),
        # One PDF per document: allow long exports, and do not retry a failed one.
        func(build_export, timeout=3600, max_tries=1),
        # No stored result, so the next "kick" with the same job id is accepted right away.
        func(dispatch_outbox, name=events.DISPATCH_JOB, keep_result=0),
        raise_overdue_events,
        raise_daily_summaries,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        # A safety net for events whose "kick" was lost (e.g. Redis was briefly down).
        cron(dispatch_outbox, name="dispatch_outbox_sweep", second={0, 30}, run_at_startup=True),
        cron(raise_overdue_events, hour={8}, minute={5}),  # 08:05 Israel time
        # Before the overdue check, so the summary counts yesterday's state.
        cron(raise_daily_summaries, hour={7}, minute={30}),
    ]
    timezone = ZoneInfo(get_settings().timezone)
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES
