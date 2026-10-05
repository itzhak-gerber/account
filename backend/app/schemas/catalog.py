import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import ItemType, VatType
from app.schemas.identity import israeli_id_checksum_ok


def _optional_tax_id(value: str) -> str:
    value = value.replace("-", "").replace(" ", "")
    if value and (not value.isdigit() or len(value) > 9 or not israeli_id_checksum_ok(value)):
        raise ValueError("invalid_tax_id")
    return value.zfill(9) if value else ""


OptionalTaxId = Annotated[str, AfterValidator(_optional_tax_id)]


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text20 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
Text30 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Text64 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
Text100 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Text2000 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class CustomerIn(BaseModel):
    name: Name
    tax_id: OptionalTaxId = ""
    email: EmailStr | None = None
    phone: Text30 = ""
    address_street: Text200 = ""
    address_city: Text100 = ""
    address_zip: Text20 = ""
    notes: Text2000 = ""


class CustomerPatch(BaseModel):
    name: Name | None = None
    tax_id: OptionalTaxId | None = None
    email: EmailStr | None = None
    phone: Text30 | None = None
    address_street: Text200 | None = None
    address_city: Text100 | None = None
    address_zip: Text20 | None = None
    notes: Text2000 | None = None
    is_archived: bool | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    tax_id: str
    email: str
    phone: str
    address_street: str
    address_city: str
    address_zip: str
    notes: str
    is_archived: bool


class ItemIn(BaseModel):
    name: Name
    description: Text2000 = ""
    item_type: ItemType = ItemType.SERVICE
    sku: Text64 = ""
    barcode: Text64 = ""
    unit_of_measure: Text20 = ""
    unit_price: Money = Decimal("0")
    vat_type: VatType = VatType.STANDARD


class ItemPatch(BaseModel):
    name: Name | None = None
    description: Text2000 | None = None
    item_type: ItemType | None = None
    sku: Text64 | None = None
    barcode: Text64 | None = None
    unit_of_measure: Text20 | None = None
    unit_price: Money | None = None
    vat_type: VatType | None = None
    is_archived: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str
    item_type: ItemType
    sku: str
    barcode: str
    unit_of_measure: str
    unit_price: Decimal
    vat_type: VatType
    is_archived: bool
