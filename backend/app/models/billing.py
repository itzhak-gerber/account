"""Plans and subscriptions: what each business bought, and what it used.

The operator defines plans (modules, price, quotas, overage prices, linkage to an index).
A business buys a plan for a period; the plan's terms at that moment are copied into the
subscription, so later changes to the plan do not touch what was bought. Without a current
subscription the business is read-only. Every issued document and every scan is recorded
as usage, with its overage price when it went past the quota.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Module(enum.StrEnum):
    INVENTORY = "inventory"  # stock, kits, goods receipts, low-stock alerts
    SCANNING = "scanning"  # photographed supplier invoices read automatically


class Linkage(enum.StrEnum):
    NONE = "none"
    CPI = "cpi"  # מדד המחירים לצרכן
    USD = "usd"  # שער הדולר


class SubscriptionKind(enum.StrEnum):
    TRIAL = "trial"
    PAID = "paid"
    UNLIMITED = "unlimited"  # businesses that existed before plans (and operator grants)


class UsageKind(enum.StrEnum):
    DOCUMENT = "document"
    SCAN = "scan"


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Plan(IdMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(f"linkage IN ({_in(Linkage)})", name="linkage"),
        CheckConstraint("duration_months > 0", name="duration_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    modules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    duration_months: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # for the whole period, before VAT
    linkage: Mapped[Linkage] = mapped_column(String(10), default=Linkage.NONE)
    # Index value the price is quoted at (the latest when the plan was saved).
    base_index: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    documents_per_month: Mapped[int | None]  # None: unlimited
    document_overage_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    scans_per_month: Mapped[int | None]  # None: unlimited
    # None: scans stop at the quota; otherwise each scan past it costs this.
    scan_overage_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True)


class BillingSettings(Base):
    """One row (id = 1): what a new business gets."""

    __tablename__ = "billing_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("trial_days >= 0", name="trial_days"),
        CheckConstraint(
            "new_business_discount_percent >= 0 AND new_business_discount_percent <= 100",
            name="discount_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    trial_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plans.id"))
    trial_days: Mapped[int] = mapped_column(default=30)
    # A discount on the first paid periods of a new business.
    new_business_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )
    new_business_discount_periods: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndexValue(IdMixin, Base):
    """CPI (by month) or the dollar rate (by day), entered by the operator."""

    __tablename__ = "index_values"
    __table_args__ = (
        UniqueConstraint("kind", "period", name="uq_index_values_kind_period"),
        CheckConstraint("kind IN ('cpi', 'usd')", name="kind"),
        CheckConstraint("value > 0", name="value_positive"),
    )

    kind: Mapped[str] = mapped_column(String(10))
    period: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(IdMixin, Base):
    """A plan bought by a business for a period. Kept forever (the billing record)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(SubscriptionKind)})", name="kind"),
        CheckConstraint("ends_on IS NULL OR ends_on > starts_on", name="period"),
        Index("ix_subscriptions_business_starts", "business_id", "starts_on"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plans.id"))
    kind: Mapped[SubscriptionKind] = mapped_column(String(10))
    # The plan's terms as bought: name, modules, quotas, prices, linkage and base index.
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)  # exclusive; None: no end
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # charged for the period, before VAT
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageEvent(IdMixin, Base):
    """One issued document or one scan, counted against the month's quota."""

    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(UsageKind)})", name="kind"),
        Index("ix_usage_events_business_month", "business_id", "kind", "month"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id"))
    kind: Mapped[UsageKind] = mapped_column(String(10))
    entity_id: Mapped[uuid.UUID]  # the document or the stored file
    month: Mapped[date] = mapped_column(Date)  # first day of the month (Israel time)
    overage_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # None: within quota
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
