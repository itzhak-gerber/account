"""The operator's screens: plans, settings, index values, subscriptions and billing.

Only for the operators named in settings (APP_OPERATOR_EMAILS), signed in with two-factor
authentication. Every change is in the audit log."""

import uuid
from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.auth.principal import CurrentPrincipal, DbSession
from app.core.db import commit
from app.reports import excel
from app.schemas.billing import (
    AdminBusinessOut,
    AssignIn,
    BillingReport,
    EndIn,
    IndexValueIn,
    IndexValueOut,
    PlanIn,
    PlanOut,
    SettingsIn,
    SettingsOut,
    SubscriptionOut,
)
from app.services import billing, plans

router = APIRouter(prefix="/admin", tags=["admin"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/plans")
async def list_plans(principal: CurrentPrincipal, session: DbSession) -> list[PlanOut]:
    plans.require_operator(principal)
    return await plans.list_plans(session)


@router.post("/plans", status_code=201)
async def create_plan(principal: CurrentPrincipal, session: DbSession, data: PlanIn) -> PlanOut:
    result = await plans.create_plan(session, principal, data)
    await commit(session)
    return result


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession, data: PlanIn
) -> PlanOut:
    result = await plans.update_plan(session, principal, plan_id, data)
    await commit(session)
    return result


@router.get("/settings")
async def get_settings(principal: CurrentPrincipal, session: DbSession) -> SettingsOut:
    plans.require_operator(principal)
    return SettingsOut.model_validate(await billing.settings(session))


@router.put("/settings")
async def put_settings(
    principal: CurrentPrincipal, session: DbSession, data: SettingsIn
) -> SettingsOut:
    result = await plans.update_settings(session, principal, data)
    await commit(session)
    return SettingsOut.model_validate(result.model_dump())


@router.get("/index-values")
async def list_index_values(principal: CurrentPrincipal, session: DbSession) -> list[IndexValueOut]:
    rows = await plans.list_index_values(session, principal)
    return [IndexValueOut.model_validate(r) for r in rows]


@router.post("/index-values", status_code=201)
async def set_index_value(
    principal: CurrentPrincipal, session: DbSession, data: IndexValueIn
) -> IndexValueOut:
    row = await plans.set_index_value(session, principal, data)
    result = IndexValueOut.model_validate(row)
    await commit(session)
    return result


@router.delete("/index-values/{value_id}", status_code=204)
async def delete_index_value(
    value_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await plans.delete_index_value(session, principal, value_id)
    await commit(session)


@router.get("/businesses")
async def list_businesses(
    principal: CurrentPrincipal, session: DbSession
) -> list[AdminBusinessOut]:
    return await plans.list_businesses(session, principal)


@router.get("/businesses/{business_id}/subscriptions")
async def list_subscriptions(
    business_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> list[SubscriptionOut]:
    rows = await plans.subscriptions(session, principal, business_id)
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.post("/businesses/{business_id}/subscriptions", status_code=201)
async def assign(
    business_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession, data: AssignIn
) -> SubscriptionOut:
    row = await plans.assign(session, principal, business_id, data)
    result = SubscriptionOut.model_validate(row)
    await commit(session)
    return result


@router.post("/businesses/{business_id}/subscriptions/{subscription_id}/end")
async def end_subscription(
    business_id: uuid.UUID,
    subscription_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
    data: EndIn,
) -> SubscriptionOut:
    row = await plans.end_subscription(
        session, principal, business_id, subscription_id, data.ends_on
    )
    result = SubscriptionOut.model_validate(row)
    await commit(session)
    return result


@router.get("/billing", response_model=None)
async def billing_report(
    principal: CurrentPrincipal,
    session: DbSession,
    month: Annotated[
        date | None, Query(description="Any day of the month; default: this month")
    ] = None,
    format: Literal["json", "xlsx"] = "json",
) -> BillingReport | Response:
    report = await plans.billing_report(session, principal, month or billing.today())
    if format == "json":
        return report
    filename = f"חיובים {report.month:%Y-%m}.xlsx"
    return Response(
        excel.billing_xlsx(report),
        media_type=XLSX,
        headers={
            "Content-Disposition": (
                f'attachment; filename="billing-{report.month:%Y-%m}.xlsx"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
