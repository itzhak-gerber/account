"""The operator's side of plans: plans, settings, index values, subscriptions and the monthly
billing report; and the business's own view of its plan and its requests to upgrade.

Prices are before VAT. A linked price follows its index: the plan's price times the latest
entered index value divided by the value the price was quoted at.
"""

import uuid
from calendar import monthrange
from dataclasses import asdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.core.config import get_settings
from app.core.db import after_commit, set_rls_context
from app.core.errors import AppError, Forbidden, NotFound
from app.emails.templates import upgrade_request_email
from app.jobs import queue
from app.models import (
    Business,
    IndexValue,
    Linkage,
    Plan,
    Subscription,
    SubscriptionKind,
    UsageEvent,
    UsageKind,
    User,
)
from app.schemas.billing import (
    AdminBusinessOut,
    AssignIn,
    BillingReport,
    IndexValueIn,
    PlanIn,
    PlanOut,
    PlanStatusOut,
    ReportRow,
    SettingsIn,
    UpgradeRequestIn,
    UsageOut,
)
from app.services import audit, billing
from app.services.permissions import Permission, require

CENT = Decimal("0.01")
ZERO = Decimal("0")


class InvalidPlan(AppError):
    status_code = 422
    code = "invalid_plan"


# --- operators -------------------------------------------------------------------------


def is_operator(principal: Principal) -> bool:
    emails = {e.strip().lower() for e in get_settings().operator_emails}
    return principal.email.lower() in emails


def require_operator(principal: Principal) -> None:
    if not is_operator(principal):
        raise Forbidden("Operators only", code="operator_only")
    if not principal.mfa:
        raise Forbidden("Two-factor authentication is required", code="mfa_required")


# --- linkage ---------------------------------------------------------------------------


async def latest_index(session: AsyncSession, kind: Linkage) -> Decimal | None:
    return await session.scalar(
        select(IndexValue.value)
        .where(IndexValue.kind == kind.value)
        .order_by(IndexValue.period.desc())
        .limit(1)
    )


async def current_price(session: AsyncSession, plan: Plan) -> Decimal | None:
    """The plan's price today, after linkage (None: the index has no value yet)."""
    if plan.linkage == Linkage.NONE:
        return plan.price
    latest = await latest_index(session, Linkage(plan.linkage))
    if latest is None or not plan.base_index:
        return None
    return (plan.price * latest / plan.base_index).quantize(CENT, ROUND_HALF_UP)


async def _plan_out(session: AsyncSession, plan: Plan) -> PlanOut:
    out = PlanOut.model_validate(plan)
    out.current_price = await current_price(session, plan)
    return out


# --- plans, settings, index values (operator) ------------------------------------------


async def list_plans(session: AsyncSession, *, active_only: bool = False) -> list[PlanOut]:
    query = select(Plan).order_by(Plan.is_active.desc(), Plan.price, Plan.name)
    if active_only:
        query = query.where(Plan.is_active.is_(True))
    return [await _plan_out(session, p) for p in await session.scalars(query)]


async def _apply_plan(session: AsyncSession, plan: Plan, data: PlanIn) -> None:
    for key, value in data.model_dump().items():
        setattr(plan, key, value)
    plan.modules = [m.value for m in data.modules]
    if plan.linkage == Linkage.NONE:
        plan.base_index = None
    elif plan.base_index is None:
        plan.base_index = await latest_index(session, Linkage(plan.linkage))
        if plan.base_index is None:
            raise InvalidPlan(
                "Enter a value of the index before linking a price to it", code="index_missing"
            )


async def create_plan(session: AsyncSession, principal: Principal, data: PlanIn) -> PlanOut:
    require_operator(principal)
    plan = Plan()
    await _apply_plan(session, plan, data)
    session.add(plan)
    await session.flush()
    await _audit(
        session, principal, "plan.created", plan.id, {"after": data.model_dump(mode="json")}
    )
    return await _plan_out(session, plan)


async def update_plan(
    session: AsyncSession, principal: Principal, plan_id: uuid.UUID, data: PlanIn
) -> PlanOut:
    """Changes apply to new purchases only: subscriptions keep the terms they bought."""
    require_operator(principal)
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise NotFound("Plan not found", code="plan_not_found")
    await _apply_plan(session, plan, data)
    await session.flush()
    await _audit(
        session, principal, "plan.updated", plan.id, {"after": data.model_dump(mode="json")}
    )
    return await _plan_out(session, plan)


async def update_settings(
    session: AsyncSession, principal: Principal, data: SettingsIn
) -> SettingsIn:
    require_operator(principal)
    if data.trial_plan_id and await session.get(Plan, data.trial_plan_id) is None:
        raise NotFound("Plan not found", code="plan_not_found")
    row = await billing.settings(session)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    await session.flush()
    await _audit(
        session,
        principal,
        "billing.settings_updated",
        None,
        {"after": data.model_dump(mode="json")},
    )
    return SettingsIn.model_validate(row, from_attributes=True)


async def set_index_value(
    session: AsyncSession, principal: Principal, data: IndexValueIn
) -> IndexValue:
    require_operator(principal)
    if data.kind == Linkage.NONE:
        raise InvalidPlan("Choose the CPI or the dollar", code="index_kind")
    period = data.period.replace(day=1) if data.kind == Linkage.CPI else data.period
    row = await session.scalar(
        select(IndexValue).where(IndexValue.kind == data.kind.value, IndexValue.period == period)
    )
    if row is None:
        row = IndexValue(kind=data.kind.value, period=period, value=data.value)
        session.add(row)
    else:
        row.value = data.value
    await session.flush()
    await _audit(
        session,
        principal,
        "billing.index_value_set",
        row.id,
        {"kind": data.kind.value, "period": period.isoformat(), "value": str(data.value)},
    )
    return row


async def list_index_values(session: AsyncSession, principal: Principal) -> list[IndexValue]:
    require_operator(principal)
    return list(
        await session.scalars(
            select(IndexValue).order_by(IndexValue.kind, IndexValue.period.desc()).limit(200)
        )
    )


async def delete_index_value(
    session: AsyncSession, principal: Principal, value_id: uuid.UUID
) -> None:
    require_operator(principal)
    row = await session.get(IndexValue, value_id)
    if row is None:
        raise NotFound("Not found", code="index_value_not_found")
    await session.delete(row)
    await _audit(
        session,
        principal,
        "billing.index_value_deleted",
        value_id,
        {"kind": row.kind, "period": row.period.isoformat()},
    )


async def _audit(
    session: AsyncSession,
    principal: Principal,
    action: str,
    entity_id: uuid.UUID | None,
    changes: dict[str, Any],
    business_id: uuid.UUID | None = None,
) -> None:
    await audit.record(
        session,
        principal,
        action=action,
        entity_type="billing",
        entity_id=entity_id,
        business_id=business_id,
        changes=changes,
    )


# --- businesses and subscriptions (operator) -------------------------------------------


async def list_businesses(session: AsyncSession, principal: Principal) -> list[AdminBusinessOut]:
    require_operator(principal)
    rows = await session.execute(
        text("SELECT * FROM admin_businesses(:day)"), {"day": billing.today()}
    )
    return [AdminBusinessOut.model_validate(dict(r._mapping)) for r in rows]


async def _enter(session: AsyncSession, business_id: uuid.UUID) -> Business:
    """The operator acts inside one business at a time (row-level security)."""
    await set_rls_context(session, business_id=business_id)
    business = await session.get(Business, business_id)
    if business is None:
        raise NotFound("Business not found", code="business_not_found")
    return business


async def subscriptions(
    session: AsyncSession, principal: Principal, business_id: uuid.UUID
) -> list[Subscription]:
    require_operator(principal)
    await _enter(session, business_id)
    return list(
        await session.scalars(
            select(Subscription)
            .where(Subscription.business_id == business_id)
            .order_by(Subscription.starts_on.desc(), Subscription.created_at.desc())
        )
    )


def add_months(day: date, months: int) -> date:
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


async def assign(
    session: AsyncSession, principal: Principal, business_id: uuid.UUID, data: AssignIn
) -> Subscription:
    """Sell a plan to a business: its terms and price are fixed now, for the whole period."""
    require_operator(principal)
    await _enter(session, business_id)
    plan = await session.get(Plan, data.plan_id)
    if plan is None:
        raise NotFound("Plan not found", code="plan_not_found")
    current = await billing.current_subscription(session, business_id)
    starts = data.starts_on
    if starts is None:
        # A renewal starts when the paid period ends; otherwise (trial, none) today.
        paid_until = current.ends_on if current and current.kind == SubscriptionKind.PAID else None
        starts = max(billing.today(), paid_until) if paid_until else billing.today()
    price = await current_price(session, plan)
    if price is None and data.price is None:
        raise InvalidPlan("The plan's index has no value", code="index_missing")
    discount = data.discount_percent
    if discount is None:
        config = await billing.settings(session)
        paid_before = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.business_id == business_id,
                Subscription.kind == SubscriptionKind.PAID,
            )
        )
        discount = (
            config.new_business_discount_percent
            if (paid_before or 0) < config.new_business_discount_periods
            else ZERO
        )
    discount = Decimal(discount).quantize(CENT)
    if data.price is not None:
        charged = data.price
    else:
        assert price is not None
        charged = (price * (100 - discount) / 100).quantize(CENT, ROUND_HALF_UP)
    terms = billing.plan_terms(plan)
    if plan.linkage != Linkage.NONE:
        terms["index_at_purchase"] = str(await latest_index(session, Linkage(plan.linkage)))
    subscription = Subscription(
        business_id=business_id,
        plan_id=plan.id,
        kind=SubscriptionKind.PAID,
        terms=terms,
        starts_on=starts,
        ends_on=add_months(starts, plan.duration_months),
        price=charged,
        discount_percent=discount,
        notes=data.notes,
        created_by_user_id=principal.user_id,
    )
    session.add(subscription)
    await session.flush()
    await _audit(
        session,
        principal,
        "subscription.created",
        subscription.id,
        {
            "plan": plan.name,
            "starts_on": starts.isoformat(),
            "ends_on": subscription.ends_on.isoformat() if subscription.ends_on else None,
            "price": str(charged),
            "discount_percent": str(discount),
        },
        business_id=business_id,
    )
    return subscription


async def end_subscription(
    session: AsyncSession,
    principal: Principal,
    business_id: uuid.UUID,
    subscription_id: uuid.UUID,
    ends_on: date,
) -> Subscription:
    """End a subscription early (or extend it): from that day the business may be read-only."""
    require_operator(principal)
    await _enter(session, business_id)
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None or subscription.business_id != business_id:
        raise NotFound("Subscription not found", code="subscription_not_found")
    if ends_on <= subscription.starts_on:
        raise InvalidPlan("The end must be after the start", code="subscription_period")
    before = subscription.ends_on
    subscription.ends_on = ends_on
    await session.flush()
    await _audit(
        session,
        principal,
        "subscription.ended",
        subscription.id,
        {"from": before.isoformat() if before else None, "to": ends_on.isoformat()},
        business_id=business_id,
    )
    return subscription


async def billing_report(session: AsyncSession, principal: Principal, month: date) -> BillingReport:
    """What to charge each business for the month: plans bought then, and overage."""
    require_operator(principal)
    month = month.replace(day=1)
    month_end = add_months(month, 1)
    rows: list[ReportRow] = []
    for business in await list_businesses(session, principal):
        await set_rls_context(session, business_id=business.id)
        bought = list(
            await session.scalars(
                select(Subscription).where(
                    Subscription.business_id == business.id,
                    Subscription.kind == SubscriptionKind.PAID,
                    Subscription.starts_on >= month,
                    Subscription.starts_on < month_end,
                )
            )
        )
        over = {
            UsageKind(kind): (count, amount or ZERO)
            for kind, count, amount in (
                await session.execute(
                    select(UsageEvent.kind, func.count(), func.sum(UsageEvent.overage_price))
                    .where(
                        UsageEvent.business_id == business.id,
                        UsageEvent.month == month,
                        UsageEvent.overage_price.is_not(None),
                    )
                    .group_by(UsageEvent.kind)
                )
            ).all()
        }
        docs = over.get(UsageKind.DOCUMENT, (0, ZERO))
        scans = over.get(UsageKind.SCAN, (0, ZERO))
        plan_charges = sum((s.price for s in bought), ZERO)
        total = plan_charges + docs[1] + scans[1]
        if not bought and not docs[0] and not scans[0]:
            continue
        rows.append(
            ReportRow(
                business_id=business.id,
                business_name=business.display_name,
                tax_id=business.tax_id,
                plan_charges=plan_charges,
                plan_names=[str(s.terms.get("name", "")) for s in bought],
                documents_over=docs[0],
                documents_over_amount=docs[1],
                scans_over=scans[0],
                scans_over_amount=scans[1],
                total=total,
            )
        )
    return BillingReport(month=month, rows=rows, total=sum((r.total for r in rows), ZERO))


# --- the business's own plan -----------------------------------------------------------


async def _usage(
    session: AsyncSession, business_id: uuid.UUID, kind: UsageKind, quota: int | None
) -> UsageOut:
    month = billing.month_of(billing.today())
    used, over, amount = (
        await session.execute(
            select(
                func.count(),
                func.count(UsageEvent.overage_price),
                func.coalesce(func.sum(UsageEvent.overage_price), 0),
            ).where(
                UsageEvent.business_id == business_id,
                UsageEvent.kind == kind,
                UsageEvent.month == month,
            )
        )
    ).one()
    return UsageOut(used=used, quota=quota, over=over, over_amount=Decimal(str(amount)))


async def status(session: AsyncSession, ctx: BusinessContext) -> PlanStatusOut:
    require(ctx, Permission.VIEW_BUSINESS)
    subscription = await billing.current_subscription(session, ctx.business_id)
    terms = subscription.terms if subscription else {}

    def money(key: str) -> Decimal | None:
        value = terms.get(key)
        return None if value is None else Decimal(str(value))

    return PlanStatusOut(
        read_only=subscription is None,
        kind=SubscriptionKind(subscription.kind) if subscription else None,
        name=terms.get("name"),
        modules=list(terms.get("modules", [])),
        starts_on=subscription.starts_on if subscription else None,
        ends_on=subscription.ends_on if subscription else None,
        document_overage_price=money("document_overage_price"),
        scan_overage_price=money("scan_overage_price"),
        documents=await _usage(
            session, ctx.business_id, UsageKind.DOCUMENT, terms.get("documents_per_month")
        ),
        scans=await _usage(session, ctx.business_id, UsageKind.SCAN, terms.get("scans_per_month")),
        available_plans=await list_plans(session, active_only=True),
    )


async def request_upgrade(
    session: AsyncSession, ctx: BusinessContext, data: UpgradeRequestIn
) -> None:
    """Owners and admins ask for a plan or a module; the operators get an email."""
    require(ctx, Permission.MANAGE_BUSINESS)
    business = await session.get(Business, ctx.business_id)
    user = await session.get(User, ctx.principal.user_id)
    assert business is not None and user is not None
    plan = await session.get(Plan, data.plan_id) if data.plan_id else None
    labels = {"inventory": "מודול מלאי", "scanning": "מודול סריקת חשבוניות"}
    wanted = (
        f"תוכנית {plan.name}"
        if plan
        else labels.get(data.module.value, data.module.value)
        if data.module
        else "שדרוג"
    )
    await audit.record(
        session,
        ctx.principal,
        action="plan.upgrade_requested",
        entity_type="business",
        entity_id=ctx.business_id,
        business_id=ctx.business_id,
        changes={"wanted": wanted, "message": data.message},
    )
    settings = get_settings()
    link = f"{settings.public_url.rstrip('/')}/admin"
    messages = [
        upgrade_request_email(
            to=operator,
            business_name=business.display_name,
            tax_id=business.tax_id,
            requested_by=f"{user.full_name} <{user.email}>",
            wanted=wanted,
            message=data.message,
            link=link,
        )
        for operator in settings.operator_emails
    ]

    async def send() -> None:
        for message in messages:
            await queue.enqueue("send_email", **asdict(message))

    after_commit(session, send)
