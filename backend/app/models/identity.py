"""Users, businesses (tenants), memberships and invitations."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class BusinessType(enum.StrEnum):
    EXEMPT_DEALER = "exempt_dealer"  # עוסק פטור
    LICENSED_DEALER = "licensed_dealer"  # עוסק מורשה
    COMPANY = "company"  # חברה בע"מ
    NONPROFIT = "nonprofit"  # עמותה / מלכ"ר


class Role(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    MEMBER = "member"
    VIEWER = "viewer"


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    idp_subject: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    locale: Mapped[str] = mapped_column(String(10), default="he")
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Business(IdMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (CheckConstraint(f"business_type IN ({_in(BusinessType)})", name="type"),)

    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(20))
    business_type: Mapped[BusinessType] = mapped_column(String(20))
    address_street: Mapped[str] = mapped_column(String(200), default="")
    address_city: Mapped[str] = mapped_column(String(100), default="")
    address_zip: Mapped[str] = mapped_column(String(20), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    default_currency: Mapped[str] = mapped_column(String(3), default="ILS")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class BusinessMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "business_members"
    __table_args__ = (
        UniqueConstraint("business_id", "user_id"),
        CheckConstraint(f"role IN ({_in(Role)})", name="role"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(String(20))

    user: Mapped[User] = relationship(lazy="raise")
    business: Mapped[Business] = relationship(lazy="raise")


class Invitation(IdMixin, TimestampMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (CheckConstraint(f"role IN ({_in(Role)})", name="role"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT)
    role: Mapped[Role] = mapped_column(String(20))
    # Snapshots shown to the invitee, who cannot read the business itself until they join.
    business_name: Mapped[str] = mapped_column(String(200))
    invited_by_name: Mapped[str] = mapped_column(String(200))
    # Only a SHA-256 hash of the token is stored; the token itself is only in the email.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    business: Mapped[Business] = relationship(lazy="raise")
