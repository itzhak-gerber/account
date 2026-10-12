import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models import Linkage, Module, SubscriptionKind

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text2000 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
UnitPrice = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
Quota = Annotated[int, Field(ge=0, le=1_000_000)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


# --- plans (operator) ------------------------------------------------------------------


class PlanIn(BaseModel):
    name: Name
    description: Text2000 = ""
    modules: list[Module] = []
    duration_months: Annotated[int, Field(ge=1, le=120)]
    price: Price
    linkage: Linkage = Linkage.NONE
    # Index the price is quoted at; None: the latest entered value of that index.
    base_index: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=4)] | None = None
    documents_per_month: Quota | None = None  # None: unlimited
    document_overage_price: UnitPrice | None = None
    scans_per_month: Quota | None = None
    scan_overage_price: UnitPrice | None = None  # None: scans stop at the quota
    is_active: bool = True

    @field_validator("modules")
    @classmethod
    def _unique(cls, value: list[Module]) -> list[Module]:
        return sorted(set(value))


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str
    modules: list[str]
    duration_months: int
    price: Decimal
    linkage: Linkage
    base_index: Decimal | None
    documents_per_month: int | None
    document_overage_price: Decimal | None
    scans_per_month: int | None
    scan_overage_price: Decimal | None
    is_active: bool
    current_price: Decimal | None = None  # after linkage; None when the index is missing


class SettingsIn(BaseModel):
    trial_plan_id: uuid.UUID | None
    trial_days: Annotated[int, Field(ge=0, le=365)]
    new_business_discount_percent: Percent
    new_business_discount_periods: Annotated[int, Field(ge=0, le=60)]


class SettingsOut(SettingsIn):
    model_config = ConfigDict(from_attributes=True)


class IndexValueIn(BaseModel):
    kind: Linkage
    period: date
    value: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=4)]


class IndexValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    period: date
    value: Decimal


# --- businesses and subscriptions (operator) -------------------------------------------


class AdminBusinessOut(BaseModel):
    id: uuid.UUID
    display_name: str
    legal_name: str
    tax_id: str
    created_at: datetime
    owner_email: str | None
    subscription_id: uuid.UUID | None
    kind: SubscriptionKind | None
    plan_name: str | None
    ends_on: date | None
    documents_this_month: int
    scans_this_month: int


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    plan_id: uuid.UUID | None
    kind: SubscriptionKind
    terms: dict[str, object]
    starts_on: date
    ends_on: date | None
    price: Decimal
    discount_percent: Decimal
    notes: str
    created_at: datetime


class AssignIn(BaseModel):
    plan_id: uuid.UUID
    starts_on: date | None = None  # default: when the current plan ends, or today
    # Override the computed price or discount (e.g. a deal agreed with the customer).
    price: Price | None = None
    discount_percent: Percent | None = None
    notes: Text2000 = ""


class EndIn(BaseModel):
    ends_on: date


class ReportRow(BaseModel):
    business_id: uuid.UUID
    business_name: str
    tax_id: str
    plan_charges: Decimal
    plan_names: list[str]
    documents_over: int
    documents_over_amount: Decimal
    scans_over: int
    scans_over_amount: Decimal
    total: Decimal


class BillingReport(BaseModel):
    month: date
    rows: list[ReportRow]
    total: Decimal


# --- the business's own plan -----------------------------------------------------------


class UsageOut(BaseModel):
    used: int
    quota: int | None
    over: int
    over_amount: Decimal


class PlanStatusOut(BaseModel):
    read_only: bool
    kind: SubscriptionKind | None
    name: str | None
    modules: list[str]
    starts_on: date | None
    ends_on: date | None
    document_overage_price: Decimal | None
    scan_overage_price: Decimal | None
    documents: UsageOut
    scans: UsageOut
    available_plans: list[PlanOut]


class UpgradeRequestIn(BaseModel):
    plan_id: uuid.UUID | None = None
    module: Module | None = None
    message: Text2000 = ""


class PlanSummary(BaseModel):
    """What the app needs everywhere: show or lock modules, warn when read-only."""

    read_only: bool
    modules: list[str]
    ends_on: date | None
