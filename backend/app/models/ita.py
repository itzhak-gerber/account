"""Israel Tax Authority allocation numbers (מספרי הקצאה, "חשבוניות ישראל").

A business connects once: its owner signs in at the tax authority and approves this software
(OAuth). The tokens are stored encrypted. Every request for a number is kept, approved or not.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class AllocationStatus(enum.StrEnum):
    APPROVED = "approved"  # the tax authority gave a number
    PENDING = "pending"  # issued without a number; retried in the background
    REJECTED = "rejected"  # the tax authority refused (e.g. the customer is not registered)


class ItaConnection(Base):
    """The tax authority tokens of one business (encrypted with the app's token key)."""

    __tablename__ = "ita_connections"

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20))  # sandbox | production
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AllocationRequest(IdMixin, Base):
    __tablename__ = "allocation_requests"
    __table_args__ = (
        Index("ix_allocation_requests_document", "document_id", "created_at"),
        CheckConstraint("status IN ('approved', 'pending', 'rejected')", name="status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    status: Mapped[AllocationStatus] = mapped_column(String(10))
    attempts: Mapped[int] = mapped_column(default=1)
    allocation_number: Mapped[str | None] = mapped_column(String(20))
    # The tax authority's message, or why it could not be reached.
    error: Mapped[str | None] = mapped_column(String(500))
    request_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
