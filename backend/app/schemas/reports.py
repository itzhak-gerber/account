"""Reports: income and VAT, money received, open balances, and the dashboard summary."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models import DocumentType, PaymentMethod

ReportName = Literal["income", "receipts", "open_balances"]
AgingBucket = Literal["current", "d1_30", "d31_60", "d61_90", "d90_plus"]


class IncomeTotals(BaseModel):
    documents: int = 0
    # Before VAT, split the way the periodic VAT return asks for it. Credit notes subtract.
    taxable: Decimal = Decimal("0.00")  # עסקאות חייבות
    zero_rated: Decimal = Decimal("0.00")  # עסקאות בשיעור אפס
    exempt: Decimal = Decimal("0.00")  # עסקאות פטורות
    net: Decimal = Decimal("0.00")
    vat: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")


class IncomeMonth(IncomeTotals):
    month: date  # first day of the month


class IncomeDocument(BaseModel):
    id: uuid.UUID
    type: DocumentType
    number: int
    issue_date: date
    customer_name: str
    customer_tax_id: str
    taxable: Decimal
    zero_rated: Decimal
    exempt: Decimal
    net: Decimal
    vat: Decimal
    total: Decimal


class IncomeReport(BaseModel):
    """Tax documents (tax invoices, invoice-receipts, credit notes) by issue date."""

    date_from: date
    date_to: date
    totals: IncomeTotals
    months: list[IncomeMonth]
    documents: list[IncomeDocument]


class ReceiptsTotals(BaseModel):
    documents: int = 0
    by_method: dict[PaymentMethod, Decimal] = {}
    total: Decimal = Decimal("0.00")


class ReceiptsMonth(ReceiptsTotals):
    month: date


class ReceiptDocument(BaseModel):
    id: uuid.UUID
    type: DocumentType
    number: int
    issue_date: date
    customer_name: str
    by_method: dict[PaymentMethod, Decimal]
    total: Decimal


class ReceiptsReport(BaseModel):
    """Money received: receipts and invoice-receipts, by issue date."""

    date_from: date
    date_to: date
    totals: ReceiptsTotals
    months: list[ReceiptsMonth]
    documents: list[ReceiptDocument]


class AgingTotals(BaseModel):
    documents: int = 0
    balance: Decimal = Decimal("0.00")
    current: Decimal = Decimal("0.00")  # not yet due
    d1_30: Decimal = Decimal("0.00")
    d31_60: Decimal = Decimal("0.00")
    d61_90: Decimal = Decimal("0.00")
    d90_plus: Decimal = Decimal("0.00")


class CustomerBalance(AgingTotals):
    customer_id: uuid.UUID | None
    customer_name: str


class OpenDocument(BaseModel):
    id: uuid.UUID
    type: DocumentType
    number: int
    issue_date: date
    due_date: date
    customer_id: uuid.UUID | None
    customer_name: str
    total: Decimal
    paid: Decimal  # paid and credited
    balance: Decimal
    days_overdue: int
    bucket: AgingBucket


class OpenBalancesReport(BaseModel):
    """Issued invoices and proformas with something left to pay, as of a date."""

    as_of: date
    totals: AgingTotals
    customers: list[CustomerBalance]
    documents: list[OpenDocument]


class MonthAmount(BaseModel):
    month: date
    amount: Decimal


class Dashboard(BaseModel):
    vat_registered: bool
    month: date
    # VAT-registered: income from tax documents. Others: money received.
    income_net: Decimal
    income_vat: Decimal
    received: Decimal
    open_balance: Decimal
    open_documents: int
    overdue_balance: Decimal
    overdue_documents: int
    # The last 12 months, oldest first: net income (or money received).
    income_by_month: list[MonthAmount]


class DailySummary(BaseModel):
    day: date
    vat_registered: bool
    issued: dict[DocumentType, int]  # documents dated that day, by type
    income_net: Decimal
    income_vat: Decimal
    received: Decimal
    open_balance: Decimal
    open_documents: int
    overdue_balance: Decimal
    overdue_documents: int
