import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import OrderStatus
from app.schemas.catalog import (
    Money,
    Name,
    OptionalTaxId,
    PositiveQuantity,
    Text20,
    Text30,
    Text100,
    Text200,
    Text2000,
)

Cost = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
InvoiceNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


# --- suppliers -------------------------------------------------------------------------


class SupplierIn(BaseModel):
    name: Name
    tax_id: OptionalTaxId = ""
    contact_name: Text200 = ""
    email: EmailStr | None = None
    phone: Text30 = ""
    address_street: Text200 = ""
    address_city: Text100 = ""
    address_zip: Text20 = ""
    notes: Text2000 = ""


class SupplierPatch(BaseModel):
    name: Name | None = None
    tax_id: OptionalTaxId | None = None
    contact_name: Text200 | None = None
    email: EmailStr | None = None
    phone: Text30 | None = None
    address_street: Text200 | None = None
    address_city: Text100 | None = None
    address_zip: Text20 | None = None
    notes: Text2000 | None = None
    is_archived: bool | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    tax_id: str
    contact_name: str
    email: str
    phone: str
    address_street: str
    address_city: str
    address_zip: str
    notes: str
    is_archived: bool


class SupplierRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


# --- purchase orders -------------------------------------------------------------------


class OrderLineIn(BaseModel):
    item_id: uuid.UUID | None = None
    description: Description
    quantity: PositiveQuantity
    unit_cost: Cost


class OrderIn(BaseModel):
    supplier_id: uuid.UUID
    order_date: date
    expected_date: date | None = None
    notes: Text2000 = ""
    lines: list[OrderLineIn] = Field(min_length=1, max_length=200)


class OrderPatch(BaseModel):
    """Only while nothing has been received."""

    supplier_id: uuid.UUID | None = None
    order_date: date | None = None
    expected_date: date | None = None
    notes: Text2000 | None = None
    lines: list[OrderLineIn] | None = Field(default=None, min_length=1, max_length=200)


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    item_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_cost: Decimal
    received_quantity: Decimal
    total: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: int
    supplier: SupplierRef
    status: OrderStatus
    order_date: date
    expected_date: date | None
    notes: str
    total: Decimal
    lines: list[OrderLineOut]
    created_at: datetime


# --- goods receipts --------------------------------------------------------------------


class ReceiptLineIn(BaseModel):
    item_id: uuid.UUID
    order_line_id: uuid.UUID | None = None
    quantity: PositiveQuantity
    unit_cost: Cost


class ReceiptIn(BaseModel):
    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None = None
    receipt_date: date
    supplier_reference: Reference = ""
    notes: Text2000 = ""
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=200)


class ReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    item_id: uuid.UUID
    order_line_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_cost: Decimal
    total: Decimal


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: int
    supplier: SupplierRef
    purchase_order_id: uuid.UUID | None
    receipt_date: date
    supplier_reference: str
    notes: str
    total: Decimal
    lines: list[ReceiptLineOut]
    created_at: datetime


# --- supplier invoices -----------------------------------------------------------------


class SupplierInvoiceIn(BaseModel):
    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None = None
    invoice_number: InvoiceNumber
    invoice_date: date
    due_date: date | None = None
    net_amount: Money
    vat_amount: Money
    paid_date: date | None = None
    notes: Text2000 = ""


class SupplierInvoicePatch(BaseModel):
    purchase_order_id: uuid.UUID | None = None
    invoice_number: InvoiceNumber | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net_amount: Money | None = None
    vat_amount: Money | None = None
    paid_date: date | None = None  # send null to mark as unpaid
    notes: Text2000 | None = None


class SupplierInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    supplier: SupplierRef
    purchase_order_id: uuid.UUID | None
    invoice_number: str
    invoice_date: date
    due_date: date | None
    net_amount: Decimal
    vat_amount: Decimal
    total: Decimal
    paid_date: date | None
    notes: str
    created_at: datetime
