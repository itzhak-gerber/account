import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class NotificationEvent(enum.StrEnum):
    PAYMENT_RECEIVED = "payment_received"  # a receipt or invoice-receipt was issued
    DOCUMENT_ISSUED = "document_issued"  # someone else (or an AI assistant) issued a document
    INVOICE_OVERDUE = "invoice_overdue"  # an invoice passed its due date unpaid
    EMAIL_FAILED = "email_failed"  # a document email to a customer could not be sent
    MEMBER_JOINED = "member_joined"  # an invited user joined the business
    DAILY_SUMMARY = "daily_summary"  # the morning summary of yesterday and open balances
    NEW_DEVICE_LOGIN = "new_device_login"  # the account was signed in from a new device


class Notification(IdMixin, Base):
    """One message in one user's in-app inbox, inside one business."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_inbox", "user_id", "business_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # None for account-level messages (e.g. a sign-in from a new device), shown in every business.
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(30))
    # Short and free of amounts or customer names (also used for email subjects and, later,
    # phone push). Details are in ``body``, shown only after login.
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="")
    link: Mapped[str] = mapped_column(String(300), default="")  # app path, e.g. /documents/<id>
    dedupe_key: Mapped[str] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    """A user's channels per event. Missing rows mean the defaults (see services)."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event: Mapped[str] = mapped_column(String(30), primary_key=True)
    channels: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class UserDevice(IdMixin, Base):
    """A browser the user has signed in from, recognised by a long-lived random cookie.
    Only a hash of the cookie is stored."""

    __tablename__ = "user_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_hash", name="uq_user_devices_device"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_hash: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(100))  # e.g. "Chrome · Windows"
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PushSubscription(IdMixin, Base):
    """A browser or installed app (PWA) that accepts Web Push for this user. The endpoint
    and keys come from the browser; together they let us push to that one device."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_device"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(1000))
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
