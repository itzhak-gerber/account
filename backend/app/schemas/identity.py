"""API / MCP data shapes for users, businesses, members and invitations."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import BusinessType, Role


def israeli_id_checksum_ok(value: str) -> bool:
    """Check digit used by Israeli ID (ת.ז), dealer (ע.מ) and company (ח.פ) numbers."""
    digits = value.zfill(9)
    if len(digits) != 9 or not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(digits):
        n = int(ch) * (1 if i % 2 == 0 else 2)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _validate_tax_id(value: str) -> str:
    value = value.replace("-", "").replace(" ", "")
    if not value.isdigit() or not 5 <= len(value) <= 9 or not israeli_id_checksum_ok(value):
        raise ValueError("invalid_tax_id")
    return value.zfill(9)


TaxId = Annotated[str, AfterValidator(_validate_tax_id)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str


class BusinessIn(BaseModel):
    legal_name: Name
    display_name: Name | None = None
    tax_id: TaxId
    business_type: BusinessType
    address_street: Short = ""
    address_city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    address_zip: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] = ""
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] = ""
    email: EmailStr | None = None


class BusinessPatch(BaseModel):
    legal_name: Name | None = None
    display_name: Name | None = None
    tax_id: TaxId | None = None
    business_type: BusinessType | None = None
    address_street: Short | None = None
    address_city: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None
    address_zip: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = (
        None
    )
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    email: EmailStr | None = None


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    legal_name: str
    display_name: str
    tax_id: str
    business_type: BusinessType
    address_street: str
    address_city: str
    address_zip: str
    phone: str
    email: str
    default_currency: str


class MembershipOut(BaseModel):
    business: BusinessOut
    role: Role


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    mfa: bool
    csrf_token: str | None = None


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: Role
    joined_at: datetime


class RoleChange(BaseModel):
    role: Role


class InvitationIn(BaseModel):
    email: EmailStr
    role: Role


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime
    created_at: datetime


class InvitationPreview(BaseModel):
    business_name: str
    invited_by_name: str
    email: str
    role: Role
    expires_at: datetime
    status: str  # pending | expired | accepted | revoked


class InvitationAccept(BaseModel):
    token: Annotated[str, StringConstraints(min_length=20, max_length=200)]


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None = None
    actor_channel: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    changes: dict[str, Any] = Field(default_factory=dict)
    ip: str | None
    created_at: datetime
