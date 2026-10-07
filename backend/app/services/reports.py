"""Reports over issued documents. Amounts come from the stored, issued totals (never recomputed),
so a report always matches the documents the customer received."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.errors import AppError
from app.models import (
    Business,
    BusinessType,
    Document,
    DocumentLine,
    DocumentPayment,
    DocumentStatus,
    DocumentType,
    PaymentMethod,
    VatType,
)
from app.schemas.reports import (
    AgingBucket,
    AgingTotals,
    CustomerBalance,
    DailySummary,
    Dashboard,
    IncomeDocument,
    IncomeMonth,
    IncomeReport,
    IncomeTotals,
    MonthAmount,
    OpenBalancesReport,
    OpenDocument,
    ReceiptDocument,
    ReceiptsMonth,
    ReceiptsReport,
    ReceiptsTotals,
)
from app.services.calc import ZERO, money
from app.services.document_rules import VAT_REGISTERED
from app.services.documents import PAYABLE, today
from app.services.permissions import Permission, require

# Documents that are sales for VAT purposes. Credit notes subtract.
SALES = (DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT, DocumentType.CREDIT_NOTE)
# Documents that record money received.
RECEIPTS = (DocumentType.RECEIPT, DocumentType.TAX_INVOICE_RECEIPT)

MAX_PERIOD_DAYS = 366 * 5


class InvalidPeriod(AppError):
    status_code = 422
    code = "invalid_period"


def _check_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise InvalidPeriod("date_from must not be after date_to")
    if (date_to - date_from).days > MAX_PERIOD_DAYS:
        raise InvalidPeriod("The period may be at most five years")


def month_start(day: date) -> date:
    return day.replace(day=1)


def months_back(day: date, count: int) -> date:
    """The first day of the month ``count`` months before ``day``'s month."""
    index = day.year * 12 + day.month - 1 - count
    return date(index // 12, index % 12 + 1, 1)


def _months(date_from: date, date_to: date) -> list[date]:
    months, current = [], month_start(date_from)
    while current <= date_to:
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def _issued(business_id: uuid.UUID, types: tuple[DocumentType, ...]) -> list[ColumnElement[bool]]:
    return [
        Document.business_id == business_id,
        Document.status == DocumentStatus.ISSUED,
        Document.type.in_(types),
    ]


# --- income and VAT --------------------------------------------------------------------


def _add_income(totals: IncomeTotals, row: IncomeDocument) -> None:
    totals.documents += 1
    totals.taxable += row.taxable
    totals.zero_rated += row.zero_rated
    totals.exempt += row.exempt
    totals.net += row.net
    totals.vat += row.vat
    totals.total += row.total


async def income(
    session: AsyncSession, ctx: BusinessContext, date_from: date, date_to: date
) -> IncomeReport:
    require(ctx.role, Permission.VIEW_REPORTS)
    return await income_for(session, ctx.business_id, date_from, date_to)


async def income_for(
    session: AsyncSession, business_id: uuid.UUID, date_from: date, date_to: date
) -> IncomeReport:
    """The income report for one business, without a permission check (internal use)."""
    _check_period(date_from, date_to)

    def line_sum(vat_type: VatType) -> ColumnElement[Decimal]:
        return func.coalesce(
            func.sum(case((DocumentLine.vat_type == vat_type, DocumentLine.line_total), else_=0)),
            0,
        )

    lines = (
        select(
            DocumentLine.document_id,
            line_sum(VatType.STANDARD).label("standard"),
            line_sum(VatType.ZERO).label("zero"),
        )
        .group_by(DocumentLine.document_id)
        .subquery()
    )
    rows = await session.execute(
        select(
            Document.id,
            Document.type,
            Document.number,
            Document.issue_date,
            Document.customer["name"].astext,
            Document.customer["tax_id"].astext,
            Document.prices_include_vat,
            Document.vat_rate,
            Document.subtotal,
            Document.vat_amount,
            Document.total,
            lines.c.standard,
            lines.c.zero,
        )
        .outerjoin(lines, lines.c.document_id == Document.id)
        .where(
            *_issued(business_id, SALES),
            Document.issue_date >= date_from,
            Document.issue_date <= date_to,
        )
        .order_by(Document.issue_date, Document.issued_at)
    )
    documents: list[IncomeDocument] = []
    for (
        doc_id,
        doc_type,
        number,
        issue_date,
        name,
        tax_id,
        prices_include_vat,
        vat_rate,
        subtotal,
        vat,
        total,
        standard,
        zero,
    ) in rows:
        if vat_rate == ZERO:
            taxable, zero_rated = ZERO, ZERO
        else:
            # Lines entered with VAT included hold the VAT inside their totals.
            taxable = (standard or ZERO) - (vat if prices_include_vat else ZERO)
            zero_rated = zero or ZERO
        exempt = subtotal - taxable - zero_rated
        credit = doc_type == DocumentType.CREDIT_NOTE

        def signed(value: Decimal, credit: bool = credit) -> Decimal:
            # Credit notes subtract; "+ ZERO" turns -0.00 into 0.00.
            return money(-value if credit else value) + ZERO

        documents.append(
            IncomeDocument(
                id=doc_id,
                type=DocumentType(doc_type),
                number=number,
                issue_date=issue_date,
                customer_name=name or "",
                customer_tax_id=tax_id or "",
                taxable=signed(taxable),
                zero_rated=signed(zero_rated),
                exempt=signed(exempt),
                net=signed(subtotal),
                vat=signed(vat),
                total=signed(total),
            )
        )

    totals = IncomeTotals()
    by_month = {m: IncomeMonth(month=m) for m in _months(date_from, date_to)}
    for row in documents:
        _add_income(totals, row)
        _add_income(by_month[month_start(row.issue_date)], row)
    return IncomeReport(
        date_from=date_from,
        date_to=date_to,
        totals=totals,
        months=list(by_month.values()),
        documents=documents,
    )


# --- money received --------------------------------------------------------------------


def _add_receipt(totals: ReceiptsTotals, row: ReceiptDocument) -> None:
    totals.documents += 1
    totals.total += row.total
    for method, amount in row.by_method.items():
        totals.by_method[method] = totals.by_method.get(method, ZERO) + amount


async def receipts(
    session: AsyncSession, ctx: BusinessContext, date_from: date, date_to: date
) -> ReceiptsReport:
    require(ctx.role, Permission.VIEW_REPORTS)
    return await receipts_for(session, ctx.business_id, date_from, date_to)


async def receipts_for(
    session: AsyncSession, business_id: uuid.UUID, date_from: date, date_to: date
) -> ReceiptsReport:
    _check_period(date_from, date_to)
    rows = await session.execute(
        select(
            Document.id,
            Document.type,
            Document.number,
            Document.issue_date,
            Document.customer["name"].astext,
            DocumentPayment.method,
            func.sum(DocumentPayment.amount),
        )
        .join(DocumentPayment, DocumentPayment.document_id == Document.id)
        .where(
            *_issued(business_id, RECEIPTS),
            Document.issue_date >= date_from,
            Document.issue_date <= date_to,
        )
        .group_by(Document.id, DocumentPayment.method)
        .order_by(Document.issue_date, Document.issued_at)
    )
    documents: dict[object, ReceiptDocument] = {}
    for doc_id, doc_type, number, issue_date, name, method, amount in rows:
        row = documents.get(doc_id)
        if row is None:
            row = documents[doc_id] = ReceiptDocument(
                id=doc_id,
                type=DocumentType(doc_type),
                number=number,
                issue_date=issue_date,
                customer_name=name or "",
                by_method={},
                total=ZERO,
            )
        row.by_method[PaymentMethod(method)] = amount
        row.total += amount

    totals = ReceiptsTotals()
    by_month = {m: ReceiptsMonth(month=m) for m in _months(date_from, date_to)}
    for row in documents.values():
        _add_receipt(totals, row)
        _add_receipt(by_month[month_start(row.issue_date)], row)
    return ReceiptsReport(
        date_from=date_from,
        date_to=date_to,
        totals=totals,
        months=list(by_month.values()),
        documents=list(documents.values()),
    )


# --- open balances ---------------------------------------------------------------------


def bucket_for(days_overdue: int) -> AgingBucket:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "d1_30"
    if days_overdue <= 60:
        return "d31_60"
    if days_overdue <= 90:
        return "d61_90"
    return "d90_plus"


def _add_open(totals: AgingTotals, row: OpenDocument) -> None:
    totals.documents += 1
    totals.balance += row.balance
    setattr(totals, row.bucket, getattr(totals, row.bucket) + row.balance)


async def open_balances(
    session: AsyncSession, ctx: BusinessContext, as_of: date | None = None
) -> OpenBalancesReport:
    require(ctx.role, Permission.VIEW_REPORTS)
    return await open_balances_for(session, ctx.business_id, as_of)


async def open_balances_for(
    session: AsyncSession, business_id: uuid.UUID, as_of: date | None = None
) -> OpenBalancesReport:
    """What customers owe now. Without a due date, a document is due on its issue date."""
    as_of = as_of or today()
    balance = Document.total - Document.amount_paid - Document.amount_credited
    rows = await session.execute(
        select(
            Document.id,
            Document.type,
            Document.number,
            Document.issue_date,
            Document.due_date,
            Document.customer_id,
            Document.customer["name"].astext,
            Document.total,
            Document.amount_paid + Document.amount_credited,
            balance,
        )
        .where(
            *_issued(business_id, tuple(PAYABLE)),
            Document.superseded_by_id.is_(None),
            balance > 0,
        )
        .order_by(func.coalesce(Document.due_date, Document.issue_date), Document.number)
    )
    documents = []
    for doc_id, doc_type, number, issue_date, due, customer_id, name, total, paid, owed in rows:
        due_date = due or issue_date
        days = (as_of - due_date).days
        documents.append(
            OpenDocument(
                id=doc_id,
                type=DocumentType(doc_type),
                number=number,
                issue_date=issue_date,
                due_date=due_date,
                customer_id=customer_id,
                customer_name=name or "",
                total=total,
                paid=paid,
                balance=owed,
                days_overdue=max(days, 0),
                bucket=bucket_for(days),
            )
        )

    totals = AgingTotals()
    customers: dict[tuple[object, str], CustomerBalance] = {}
    for row in documents:
        _add_open(totals, row)
        key = (row.customer_id, row.customer_name)
        customer = customers.setdefault(
            key, CustomerBalance(customer_id=row.customer_id, customer_name=row.customer_name)
        )
        _add_open(customer, row)
    return OpenBalancesReport(
        as_of=as_of,
        totals=totals,
        customers=sorted(customers.values(), key=lambda c: c.balance, reverse=True),
        documents=documents,
    )


# --- dashboard -------------------------------------------------------------------------


async def dashboard(session: AsyncSession, ctx: BusinessContext) -> Dashboard:
    require(ctx.role, Permission.VIEW_REPORTS)
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    vat_registered = BusinessType(business.business_type) in VAT_REGISTERED
    now = today()
    this_month = month_start(now)
    first = months_back(now, 11)  # 12 months including this one
    sales = await income(session, ctx, first, now)
    received = await receipts(session, ctx, first, now)
    balances = await open_balances(session, ctx, now)
    current_sales = sales.months[-1]
    overdue = [d for d in balances.documents if d.bucket != "current"]
    series = (
        [MonthAmount(month=m.month, amount=m.net) for m in sales.months]
        if vat_registered
        else [MonthAmount(month=m.month, amount=m.total) for m in received.months]
    )
    return Dashboard(
        vat_registered=vat_registered,
        month=this_month,
        income_net=current_sales.net,
        income_vat=current_sales.vat,
        received=received.months[-1].total,
        open_balance=balances.totals.balance,
        open_documents=balances.totals.documents,
        overdue_balance=sum((d.balance for d in overdue), money(ZERO)),
        overdue_documents=len(overdue),
        income_by_month=series,
    )


# --- daily summary ---------------------------------------------------------------------


async def daily_summary_for(
    session: AsyncSession, business_id: uuid.UUID, day: date
) -> DailySummary:
    """What happened on ``day`` and where the business stands now (for the morning email)."""
    business = await session.get(Business, business_id)
    assert business is not None
    counts = dict(
        (
            await session.execute(
                select(Document.type, func.count())
                .where(
                    Document.business_id == business_id,
                    Document.status == DocumentStatus.ISSUED,
                    Document.issue_date == day,
                )
                .group_by(Document.type)
            )
        ).all()
    )
    sales = await income_for(session, business_id, day, day)
    received = await receipts_for(session, business_id, day, day)
    balances = await open_balances_for(session, business_id, today())
    overdue = [d for d in balances.documents if d.bucket != "current"]
    return DailySummary(
        day=day,
        vat_registered=BusinessType(business.business_type) in VAT_REGISTERED,
        issued={DocumentType(t): n for t, n in counts.items()},
        income_net=sales.totals.net,
        income_vat=sales.totals.vat,
        received=received.totals.total,
        open_balance=balances.totals.balance,
        open_documents=balances.totals.documents,
        overdue_balance=sum((d.balance for d in overdue), money(ZERO)),
        overdue_documents=len(overdue),
    )
