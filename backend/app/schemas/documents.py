import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models import DocumentStatus, DocumentType, PaymentMethod, RelationType, VatType
from app.schemas.catalog import OptionalTaxId, Text20, Text30, Text100, Text200, Text2000

# superseded: a proforma replaced by the tax invoice issued from it.
PaymentStatus = Literal["unpaid", "partial", "paid", "superseded"]
# Delivery notes: "invoiced" once an issued invoice bills them.
DeliveryNoteStatus = Literal["open", "invoiced"]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class CustomerDetails(BaseModel):
    """The customer as printed on the document."""

    name: Text200 = ""
    tax_id: OptionalTaxId = ""
    email: EmailStr | None = None
    phone: Text30 = ""
    address_street: Text200 = ""
    address_city: Text100 = ""
    address_zip: Text20 = ""


class LineIn(BaseModel):
    item_id: uuid.UUID | None = None
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    quantity: Quantity = Decimal("1")
    unit_of_measure: Text20 = ""
    unit_price: Money
    discount_percent: Percent = Decimal("0")
    vat_type: VatType = VatType.STANDARD


class PaymentDetails(BaseModel):
    bank: Text30 = ""
    branch: Text20 = ""
    account: Text30 = ""
    check_number: Text30 = ""
    card_last4: Annotated[str, StringConstraints(pattern=r"^(\d{4})?$")] = ""
    installments: Annotated[int, Field(ge=1, le=36)] | None = None
    reference: Text100 = ""


class PaymentIn(BaseModel):
    method: PaymentMethod
    amount: PositiveMoney
    payment_date: date
    details: PaymentDetails = PaymentDetails()


class AllocationIn(BaseModel):
    """Part of a receipt applied to an issued invoice (tax invoice or proforma)."""

    invoice_id: uuid.UUID
    amount: PositiveMoney


class AllocationOut(BaseModel):
    invoice_id: uuid.UUID
    invoice_type: DocumentType
    invoice_number: int | None
    invoice_date: date
    invoice_total: Decimal
    amount: Decimal
    balance_due: Decimal


class DocumentIn(BaseModel):
    type: DocumentType
    issue_date: date | None = None
    due_date: date | None = None
    customer_id: uuid.UUID | None = None
    customer: CustomerDetails | None = None
    prices_include_vat: bool = False
    returns_stock: bool = True  # credit notes: bring the goods back into stock
    lines: Annotated[list[LineIn], Field(max_length=200)] = []
    payments: Annotated[list[PaymentIn], Field(max_length=20)] = []
    allocations: Annotated[list[AllocationIn], Field(max_length=50)] = []
    notes: Text2000 = ""


class DocumentPatch(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None
    customer_id: uuid.UUID | None = None
    customer: CustomerDetails | None = None
    prices_include_vat: bool | None = None
    returns_stock: bool | None = None
    lines: Annotated[list[LineIn], Field(max_length=200)] | None = None
    payments: Annotated[list[PaymentIn], Field(max_length=20)] | None = None
    allocations: Annotated[list[AllocationIn], Field(max_length=50)] | None = None
    notes: Text2000 | None = None


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    item_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_of_measure: str
    unit_price: Decimal
    discount_percent: Decimal
    vat_type: VatType
    line_total: Decimal


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    method: PaymentMethod
    amount: Decimal
    payment_date: date
    details: dict[str, object]

    @field_validator("details", mode="before")
    @classmethod
    def _drop_empty(cls, value: dict[str, object]) -> dict[str, object]:
        return {k: v for k, v in (value or {}).items() if v not in ("", None)}


class RelatedDocument(BaseModel):
    id: uuid.UUID
    type: DocumentType
    number: int | None
    status: DocumentStatus
    relation: RelationType
    amount: Decimal | None = None
    # "outgoing": this document → related (e.g. credit note → invoice); "incoming": the reverse.
    direction: str


class DocumentOut(BaseModel):
    id: uuid.UUID
    type: DocumentType
    title: str
    status: DocumentStatus
    number: int | None
    issue_date: date
    due_date: date | None
    customer_id: uuid.UUID | None
    customer: CustomerDetails
    currency: str
    prices_include_vat: bool
    returns_stock: bool
    vat_rate: Decimal
    subtotal: Decimal
    discount_total: Decimal
    vat_amount: Decimal
    total: Decimal
    notes: str
    allocation_number: str | None
    # Invoices only: what is paid, credited and still open.
    payment_status: PaymentStatus | None
    delivery_status: DeliveryNoteStatus | None
    amount_paid: Decimal
    amount_credited: Decimal
    balance_due: Decimal | None
    allocations: list[AllocationOut]
    deliveries: list["DeliveryOut"]
    lines: list[LineOut]
    payments: list[PaymentOut]
    related: list[RelatedDocument]
    original_delivered_at: datetime | None
    issued_at: datetime | None
    created_at: datetime


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: DocumentType
    status: DocumentStatus
    number: int | None
    issue_date: date
    customer_name: str
    total: Decimal
    payment_status: PaymentStatus | None = None
    balance_due: Decimal | None = None
    delivery_status: DeliveryNoteStatus | None = None
    created_at: datetime


class ConvertIn(BaseModel):
    type: DocumentType


class InvoiceDeliveryNotesIn(BaseModel):
    delivery_note_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    type: DocumentType = DocumentType.TAX_INVOICE


class NumberingOut(BaseModel):
    next_numbers: dict[DocumentType, int]


class NumberingIn(BaseModel):
    type: DocumentType
    next_number: Annotated[int, Field(ge=1, le=99_999_999)]


class DocumentTypeInfo(BaseModel):
    type: DocumentType
    title: str
    has_lines: bool
    has_payments: bool
    is_tax_document: bool
    shows_vat: bool
    has_due_date: bool


class EmailRequest(BaseModel):
    to: Annotated[list[EmailStr], Field(min_length=1, max_length=5)]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    message: Annotated[str, StringConstraints(max_length=4000)] = ""


class EmailDefaults(BaseModel):
    to: list[str]
    subject: str
    message: str


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    recipients: list[str]
    subject: str
    variant: str
    status: str
    error: str | None
    sent_at: datetime | None
    created_at: datetime


DocumentOut.model_rebuild()
