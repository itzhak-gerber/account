"""Subscriptions in use: what a business may do now, its trial, and its usage.

Quotas are per calendar month in Israel time. An issued document past the month's quota is
still issued and recorded with the plan's overage price; a scan past the quota is recorded
with its overage price, or refused when the plan sets none.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BillingSettings,
    DocumentType,
    Plan,
    Subscription,
    SubscriptionKind,
    UsageEvent,
    UsageKind,
)
from app.services.access import Access, QuotaExceeded

ISRAEL = ZoneInfo("Asia/Jerusalem")

# Quotes are offers, not records of business: they are not counted.
UNCOUNTED_DOCUMENTS = frozenset({DocumentType.QUOTE})


def today() -> date:
    return datetime.now(UTC).astimezone(ISRAEL).date()


def month_of(day: date) -> date:
    return day.replace(day=1)


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def plan_terms(plan: Plan) -> dict[str, Any]:
    """The plan as bought: copied into the subscription so later edits do not change it."""
    return {
        "name": plan.name,
        "modules": sorted(plan.modules),
        "duration_months": plan.duration_months,
        "price": _money(plan.price),
        "linkage": plan.linkage,
        "base_index": None if plan.base_index is None else str(plan.base_index),
        "documents_per_month": plan.documents_per_month,
        "document_overage_price": _money(plan.document_overage_price),
        "scans_per_month": plan.scans_per_month,
        "scan_overage_price": _money(plan.scan_overage_price),
    }


async def current_subscription(
    session: AsyncSession, business_id: uuid.UUID, on: date | None = None, *, lock: bool = False
) -> Subscription | None:
    on = on or today()
    query = (
        select(Subscription)
        .where(
            Subscription.business_id == business_id,
            Subscription.starts_on <= on,
            (Subscription.ends_on.is_(None)) | (Subscription.ends_on > on),
        )
        .order_by(Subscription.starts_on.desc(), Subscription.created_at.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


def access_of(subscription: Subscription | None) -> Access:
    if subscription is None:
        return Access(subscription_id=None)
    return Access(
        subscription_id=subscription.id,
        modules=frozenset(subscription.terms.get("modules", [])),
        ends_on=subscription.ends_on,
        terms=subscription.terms,
    )


async def access_for(session: AsyncSession, business_id: uuid.UUID) -> Access:
    return access_of(await current_subscription(session, business_id))


async def settings(session: AsyncSession) -> BillingSettings:
    row = await session.get(BillingSettings, 1)
    if row is None:  # the migration creates it; this keeps an empty database working
        row = BillingSettings(id=1, trial_days=30)
        session.add(row)
        await session.flush()
    return row


async def start_trial(
    session: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID
) -> Subscription | None:
    """A new business's free trial, as the operator set it (none: it starts read-only)."""
    config = await settings(session)
    plan = await session.get(Plan, config.trial_plan_id) if config.trial_plan_id else None
    if plan is None or config.trial_days <= 0:
        return None
    start = today()
    subscription = Subscription(
        business_id=business_id,
        plan_id=plan.id,
        kind=SubscriptionKind.TRIAL,
        terms=plan_terms(plan),
        starts_on=start,
        ends_on=start + timedelta(days=config.trial_days),
        price=Decimal("0"),
        discount_percent=Decimal("0"),
        notes="תקופת ניסיון",
        created_by_user_id=user_id,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def used_this_month(
    session: AsyncSession, business_id: uuid.UUID, kind: UsageKind, month: date | None = None
) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.business_id == business_id,
            UsageEvent.kind == kind,
            UsageEvent.month == (month or month_of(today())),
        )
    )
    return count or 0


_QUOTA = {UsageKind.DOCUMENT: "documents_per_month", UsageKind.SCAN: "scans_per_month"}
_OVERAGE = {UsageKind.DOCUMENT: "document_overage_price", UsageKind.SCAN: "scan_overage_price"}


async def check_scan_allowed(session: AsyncSession, business_id: uuid.UUID) -> None:
    """Refuse a scan past the month's quota when the plan charges nothing for more."""
    subscription = await current_subscription(session, business_id)
    if subscription is None:
        return  # the caller's module check has already refused it
    quota = subscription.terms.get(_QUOTA[UsageKind.SCAN])
    if quota is None or subscription.terms.get(_OVERAGE[UsageKind.SCAN]) is not None:
        return
    if await used_this_month(session, business_id, UsageKind.SCAN) >= quota:
        raise QuotaExceeded(
            "This month's scans are used up", code="scan_quota_exceeded", quota=quota
        )


async def record_usage(
    session: AsyncSession, business_id: uuid.UUID, kind: UsageKind, entity_id: uuid.UUID
) -> UsageEvent | None:
    """Count one document or scan against the current subscription's month."""
    # Locked so two issues at once cannot both take the last place in the quota.
    subscription = await current_subscription(session, business_id, lock=True)
    if subscription is None:
        return None
    month = month_of(today())
    quota = subscription.terms.get(_QUOTA[kind])
    overage: Decimal | None = None
    if quota is not None and await used_this_month(session, business_id, kind, month) >= quota:
        price = subscription.terms.get(_OVERAGE[kind])
        overage = Decimal(price) if price is not None else Decimal("0")
    event = UsageEvent(
        business_id=business_id,
        subscription_id=subscription.id,
        kind=kind,
        entity_id=entity_id,
        month=month,
        overage_price=overage,
    )
    session.add(event)
    await session.flush()
    return event
