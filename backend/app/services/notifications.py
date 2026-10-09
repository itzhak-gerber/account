"""Notifications: turn domain events into in-app messages (and emails, by preference).

Recipients are chosen by role inside the business. Whoever caused an event is not told about
it, unless an AI assistant (MCP) acted for them. Titles stay free of amounts and customer
names, because they are also used as email subjects (and later phone push); the details are in
the body, which is only shown after login.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.core.config import get_settings
from app.core.db import after_commit
from app.emails.templates import notification_email
from app.jobs import queue
from app.models import (
    Business,
    BusinessMember,
    Document,
    DocumentType,
    Notification,
    NotificationEvent,
    NotificationPreference,
    Role,
    User,
)
from app.schemas.notifications import ChannelPrefs, NotificationOut, PreferenceOut
from app.services import push, reports
from app.services.document_rules import RULES

CHANNELS = ("in_app", "email")

# Email is on by default only for what usually needs action.
DEFAULTS: dict[NotificationEvent, dict[str, bool]] = {
    NotificationEvent.PAYMENT_RECEIVED: {"in_app": True, "email": False, "push": True},
    NotificationEvent.DOCUMENT_ISSUED: {"in_app": True, "email": False, "push": False},
    NotificationEvent.INVOICE_OVERDUE: {"in_app": True, "email": True, "push": True},
    NotificationEvent.EMAIL_FAILED: {"in_app": True, "email": True, "push": True},
    NotificationEvent.MEMBER_JOINED: {"in_app": True, "email": False, "push": False},
    # A summary is an email; in the app the dashboard already shows the same numbers.
    NotificationEvent.DAILY_SUMMARY: {"in_app": False, "email": True, "push": False},
    NotificationEvent.NEW_DEVICE_LOGIN: {"in_app": True, "email": True, "push": True},
}

MANAGERS = frozenset({Role.OWNER, Role.ADMIN})
EVENT_ROLES: dict[NotificationEvent, frozenset[Role]] = {
    NotificationEvent.PAYMENT_RECEIVED: MANAGERS | {Role.ACCOUNTANT},
    NotificationEvent.DOCUMENT_ISSUED: MANAGERS,
    NotificationEvent.INVOICE_OVERDUE: MANAGERS | {Role.ACCOUNTANT},
    NotificationEvent.MEMBER_JOINED: MANAGERS,
    NotificationEvent.EMAIL_FAILED: frozenset(),  # only the person who sent it
    NotificationEvent.DAILY_SUMMARY: MANAGERS | {Role.ACCOUNTANT},
    NotificationEvent.NEW_DEVICE_LOGIN: frozenset(),  # the account holder (see devices.py)
}


@dataclass(frozen=True)
class Message:
    event: NotificationEvent
    title: str
    body: str
    link: str
    dedupe_key: str
    roles: frozenset[Role]
    # Always included (e.g. the sender of a failed email); never excluded as the actor.
    direct_user_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    # Label/value rows added to the email (only for messages meant to carry figures).
    details: tuple[tuple[str, str], ...] = ()
    # The email's first line; "{business}" is replaced with the business name.
    intro: str | None = None


def format_ils(value: Any) -> str:
    return f"{Decimal(str(value)):,.2f} ₪"  # as the app shows amounts


def _uuid(value: Any) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def _doc_name(doc_type: str, number: Any) -> str:
    return f"{RULES[DocumentType(doc_type)].title_he} מס׳ {number}"


# --- events → messages -----------------------------------------------------------------


def _from_document_issued(event_id: uuid.UUID, payload: dict[str, Any]) -> Message:
    doc_type = DocumentType(payload["type"])
    name = _doc_name(doc_type, payload["number"])
    customer = payload.get("customer_name") or ""
    amount = format_ils(payload.get("total", "0"))
    via_ai = payload.get("channel") == "mcp"
    by = payload.get("actor_name") or ""
    # Something an AI assistant did on a user's behalf is news to that user too.
    actor = None if via_ai else _uuid(payload.get("actor_user_id"))
    link = f"/documents/{payload['document_id']}"
    if doc_type in (DocumentType.RECEIPT, DocumentType.TAX_INVOICE_RECEIPT):
        return Message(
            event=NotificationEvent.PAYMENT_RECEIVED,
            title="התקבל תשלום",
            body=f"{name}{f' מ{customer}' if customer else ''}: {amount}",
            link=link,
            dedupe_key=f"event:{event_id}",
            roles=EVENT_ROLES[NotificationEvent.PAYMENT_RECEIVED],
            actor_user_id=actor,
        )
    who = "עוזר AI" if via_ai else by
    return Message(
        event=NotificationEvent.DOCUMENT_ISSUED,
        title=f"הופק מסמך חדש{' על ידי עוזר AI' if via_ai else ''}",
        body=(
            f"{name}{f' ל{customer}' if customer else ''}: {amount}"
            + (f" · הופק על ידי {who}" if who else "")
        ),
        link=link,
        dedupe_key=f"event:{event_id}",
        roles=EVENT_ROLES[NotificationEvent.DOCUMENT_ISSUED],
        actor_user_id=actor,
    )


async def _from_invoice_overdue(session: AsyncSession, payload: dict[str, Any]) -> Message | None:
    document = await session.get(Document, uuid.UUID(payload["document_id"]))
    if document is None:
        return None
    balance = document.total - document.amount_paid - document.amount_credited
    if balance <= 0 or document.superseded_by_id is not None:
        return None  # paid since the event was raised
    customer = (document.customer or {}).get("name", "")
    due = datetime.fromisoformat(payload["due_date"]).strftime("%d/%m/%Y")
    return Message(
        event=NotificationEvent.INVOICE_OVERDUE,
        title="חשבונית לא שולמה במועד",
        body=(
            f"{_doc_name(document.type, document.number)}"
            f"{f' של {customer}' if customer else ''}: יתרה {format_ils(balance)}, "
            f"לתשלום עד {due}"
        ),
        link=f"/documents/{document.id}",
        dedupe_key=f"overdue:{document.id}",
        roles=EVENT_ROLES[NotificationEvent.INVOICE_OVERDUE],
    )


def _from_email_failed(payload: dict[str, Any]) -> Message:
    return Message(
        event=NotificationEvent.EMAIL_FAILED,
        title="שליחת מסמך במייל נכשלה",
        body=(
            f"{_doc_name(payload['type'], payload['number'])} לא נשלח אל "
            f"{', '.join(payload.get('to', []))}. אפשר לבדוק את הכתובת ולשלוח שוב."
        ),
        link=f"/documents/{payload['document_id']}",
        dedupe_key=f"email_failed:{payload['delivery_id']}",
        roles=EVENT_ROLES[NotificationEvent.EMAIL_FAILED],
        direct_user_id=_uuid(payload.get("created_by_user_id")),
    )


def _from_member_joined(event_id: uuid.UUID, payload: dict[str, Any]) -> Message:
    name = payload.get("name") or payload.get("email", "")
    return Message(
        event=NotificationEvent.MEMBER_JOINED,
        title="משתמש/ת חדש/ה הצטרף/ה לעסק",
        body=f"{name} קיבל/ה את ההזמנה והצטרף/ה לעסק.",
        link="/settings?tab=team",
        dedupe_key=f"event:{event_id}",
        roles=EVENT_ROLES[NotificationEvent.MEMBER_JOINED],
        actor_user_id=_uuid(payload.get("user_id")),
    )


def _documents(count: int) -> str:
    return "מסמך אחד" if count == 1 else f"{count} מסמכים"


def _he_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


async def _from_daily_summary(
    session: AsyncSession, business_id: uuid.UUID, payload: dict[str, Any]
) -> Message | None:
    day = date.fromisoformat(payload["day"])
    summary = await reports.daily_summary_for(session, business_id, day)
    issued_total = sum(summary.issued.values())
    if issued_total == 0 and summary.open_balance <= 0:
        return None  # a quiet day with nothing owed: no email
    issued_text = (
        ", ".join(
            f"{count} {RULES[doc_type].title_he}"
            for doc_type, count in sorted(summary.issued.items(), key=lambda kv: -kv[1])
        )
        or "לא הופקו מסמכים"
    )
    details: list[tuple[str, str]] = [("מסמכים שהופקו", issued_text)]
    if summary.vat_registered:
        details += [
            ("הכנסות לפני מע״מ", format_ils(summary.income_net)),
            ("מע״מ עסקאות", format_ils(summary.income_vat)),
        ]
    details += [
        ("תקבולים", format_ils(summary.received)),
        (
            "יתרות פתוחות",
            f"{format_ils(summary.open_balance)} ({_documents(summary.open_documents)})",
        ),
        (
            "מתוכן באיחור",
            f"{format_ils(summary.overdue_balance)} ({_documents(summary.overdue_documents)})",
        ),
    ]
    return Message(
        event=NotificationEvent.DAILY_SUMMARY,
        title=f"סיכום יומי ל-{_he_date(day)}",
        body=(
            f"הופקו {_documents(issued_total)}, התקבלו {format_ils(summary.received)}. "
            f"יתרות פתוחות {format_ils(summary.open_balance)}, "
            f"מתוכן באיחור {format_ils(summary.overdue_balance)}."
        ),
        link="/",
        dedupe_key=f"summary:{day.isoformat()}",
        roles=EVENT_ROLES[NotificationEvent.DAILY_SUMMARY],
        details=tuple(details),
        intro="סיכום הפעילות בעסק {business} ביום " + _he_date(day) + ":",
    )


async def message_for(
    session: AsyncSession,
    business_id: uuid.UUID,
    event_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> Message | None:
    if event_type == "document.issued":
        return _from_document_issued(event_id, payload)
    if event_type == "invoice.overdue":
        return await _from_invoice_overdue(session, payload)
    if event_type == "document.email_failed":
        return _from_email_failed(payload)
    if event_type == "member.joined":
        return _from_member_joined(event_id, payload)
    if event_type == "business.daily_summary":
        return await _from_daily_summary(session, business_id, payload)
    return None  # not every event notifies anyone


# --- dispatch --------------------------------------------------------------------------


async def preferences_for(
    session: AsyncSession, user_ids: list[uuid.UUID], event: NotificationEvent
) -> dict[uuid.UUID, dict[str, bool]]:
    stored = {
        row.user_id: row.channels
        for row in await session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id.in_(user_ids),
                NotificationPreference.event == event,
            )
        )
    }
    return {
        user_id: {**DEFAULTS[event], **{k: bool(v) for k, v in stored.get(user_id, {}).items()}}
        for user_id in user_ids
    }


async def deliver(session: AsyncSession, business_id: uuid.UUID, message: Message) -> int:
    """Write the message to each recipient's inbox and queue emails. Runs inside the
    business's security context; returns how many inboxes received it."""
    members = (
        await session.execute(
            select(BusinessMember.user_id, BusinessMember.role).where(
                BusinessMember.business_id == business_id
            )
        )
    ).all()
    recipients = [
        user_id
        for user_id, role in members
        if (Role(role) in message.roles and user_id != message.actor_user_id)
        or user_id == message.direct_user_id
    ]
    if not recipients:
        return 0
    prefs = await preferences_for(session, recipients, message.event)
    in_app = [u for u in recipients if prefs[u]["in_app"]]
    delivered = 0
    for user_id in in_app:
        # One row at a time: the worker may write but never read inboxes (row-level security),
        # so "already notified" shows up as a unique-key conflict, not as a lookup.
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(Notification).values(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        business_id=business_id,
                        event=message.event.value,
                        title=message.title,
                        body=message.body[:500],
                        link=message.link,
                        dedupe_key=message.dedupe_key,
                    )
                )
            delivered += 1
        except IntegrityError:
            continue
    push.queue_push(
        session,
        [u for u in recipients if prefs[u]["push"]],
        title=message.title,
        link=message.link,
        tag=message.dedupe_key,
    )
    by_email = [u for u in recipients if prefs[u]["email"]]
    if by_email:
        business = await session.get(Business, business_id)
        assert business is not None
        emails = list(await session.scalars(select(User.email).where(User.id.in_(by_email))))
        link = f"{get_settings().public_url.rstrip('/')}{message.link}"
        for address in emails:
            email = notification_email(
                to=address,
                business_name=business.display_name,
                title=message.title,
                link=link,
                details=message.details,
                intro=(
                    message.intro.replace("{business}", business.display_name)
                    if message.intro
                    else None
                ),
            )

            async def send(email: Any = email) -> None:
                await queue.enqueue(
                    "send_email",
                    to=email.to,
                    subject=email.subject,
                    html=email.html,
                    text=email.text,
                )

            after_commit(session, send)
    return delivered


# --- inbox -----------------------------------------------------------------------------


def _inbox(ctx: BusinessContext) -> list[Any]:
    # This business's notifications, plus account-level ones (shown in every business).
    return [
        Notification.user_id == ctx.principal.user_id,
        or_(Notification.business_id == ctx.business_id, Notification.business_id.is_(None)),
    ]


async def list_notifications(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    unread_only: bool = False,
    limit: int = 30,
    before: datetime | None = None,
) -> list[NotificationOut]:
    query = select(Notification).where(*_inbox(ctx))
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if before:
        query = query.where(Notification.created_at < before)
    rows = await session.scalars(
        query.order_by(Notification.created_at.desc()).limit(min(limit, 100))
    )
    return [NotificationOut.model_validate(n) for n in rows]


async def unread_count(session: AsyncSession, ctx: BusinessContext) -> int:
    count = await session.scalar(
        select(func.count()).where(*_inbox(ctx), Notification.read_at.is_(None))
    )
    return int(count or 0)


async def mark_read(
    session: AsyncSession, ctx: BusinessContext, ids: list[uuid.UUID] | None = None
) -> int:
    """Mark the given notifications (or all of them, when ``ids`` is None) as read."""
    statement = (
        update(Notification)
        .where(*_inbox(ctx), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    if ids is not None:
        statement = statement.where(Notification.id.in_(ids))
    result = await session.execute(statement)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


# --- preferences -----------------------------------------------------------------------


async def get_preferences(session: AsyncSession, principal: Principal) -> list[PreferenceOut]:
    stored = {
        row.event: row.channels
        for row in await session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == principal.user_id
            )
        )
    }
    return [
        PreferenceOut(
            event=event,
            channels=ChannelPrefs(**{**DEFAULTS[event], **stored.get(event.value, {})}),
        )
        for event in NotificationEvent
    ]


async def set_preferences(
    session: AsyncSession, principal: Principal, changes: dict[NotificationEvent, ChannelPrefs]
) -> list[PreferenceOut]:
    for event, channels in changes.items():
        await session.execute(
            insert(NotificationPreference)
            .values(user_id=principal.user_id, event=event.value, channels=channels.model_dump())
            .on_conflict_do_update(
                index_elements=["user_id", "event"], set_={"channels": channels.model_dump()}
            )
        )
    return await get_preferences(session, principal)
