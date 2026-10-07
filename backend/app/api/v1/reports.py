from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.auth.principal import CurrentBusiness, DbSession
from app.models import Business
from app.reports import excel
from app.schemas.reports import (
    Dashboard,
    IncomeReport,
    OpenBalancesReport,
    ReceiptsReport,
    ReportName,
)
from app.services import reports
from app.services.documents import today

router = APIRouter(prefix="/businesses/{business_id}/reports", tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TITLES: dict[ReportName, str] = {
    "income": "הכנסות ומעמ",
    "receipts": "תקבולים",
    "open_balances": "חובות פתוחים",
}

DateFrom = Annotated[date | None, Query(description="Default: the first day of this month")]
DateTo = Annotated[date | None, Query(description="Default: today")]


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    now = today()
    return date_from or reports.month_start(now), date_to or now


@router.get("/dashboard")
async def dashboard(ctx: CurrentBusiness, session: DbSession) -> Dashboard:
    return await reports.dashboard(session, ctx)


@router.get("/income")
async def income(
    ctx: CurrentBusiness, session: DbSession, date_from: DateFrom = None, date_to: DateTo = None
) -> IncomeReport:
    return await reports.income(session, ctx, *_period(date_from, date_to))


@router.get("/receipts")
async def receipts(
    ctx: CurrentBusiness, session: DbSession, date_from: DateFrom = None, date_to: DateTo = None
) -> ReceiptsReport:
    return await reports.receipts(session, ctx, *_period(date_from, date_to))


@router.get("/open-balances")
async def open_balances(ctx: CurrentBusiness, session: DbSession) -> OpenBalancesReport:
    return await reports.open_balances(session, ctx)


@router.get("/{report}.xlsx", response_class=Response)
async def export_xlsx(
    report: ReportName,
    ctx: CurrentBusiness,
    session: DbSession,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Response:
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    start, end = _period(date_from, date_to)
    content: bytes
    if report == "income":
        content = excel.income_xlsx(
            await reports.income(session, ctx, start, end), business.display_name
        )
        suffix = f"{start:%Y-%m-%d} עד {end:%Y-%m-%d}"
    elif report == "receipts":
        content = excel.receipts_xlsx(
            await reports.receipts(session, ctx, start, end), business.display_name
        )
        suffix = f"{start:%Y-%m-%d} עד {end:%Y-%m-%d}"
    else:
        balances = await reports.open_balances(session, ctx)
        content = excel.open_balances_xlsx(balances, business.display_name)
        suffix = f"{balances.as_of:%Y-%m-%d}"
    filename = f"{TITLES[report]} {suffix}.xlsx"
    ascii_name = f"{report}-{suffix.replace(' עד ', '-')}.xlsx"
    return Response(
        content,
        media_type=XLSX,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "no-store",
        },
    )
