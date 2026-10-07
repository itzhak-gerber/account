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


class Notification(IdMixin, Base):
    """One message in one user's in-app inbox, inside one business."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_inbox", "user_id", "business_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    business_id: Mapped[uuid.UUID] = mapped_column(
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
