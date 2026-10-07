"""SQLAlchemy models. Import every model module here so Alembic sees it."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.catalog import Customer, Item, ItemType, VatType
from app.models.documents import (
    DeliveryStatus,
    Document,
    DocumentDelivery,
    DocumentLine,
    DocumentPayment,
    DocumentRelation,
    DocumentSequence,
    DocumentStatus,
    DocumentType,
    OutboxEvent,
    PaymentMethod,
    RelationType,
    StoredFile,
    VatRate,
)
from app.models.identity import Business, BusinessMember, BusinessType, Invitation, Role, User
from app.models.notifications import (
    Notification,
    NotificationEvent,
    NotificationPreference,
    UserDevice,
)

__all__ = [
    "AuditLog",
    "Base",
    "Business",
    "BusinessMember",
    "BusinessType",
    "Customer",
    "DeliveryStatus",
    "Document",
    "DocumentDelivery",
    "DocumentLine",
    "DocumentPayment",
    "DocumentRelation",
    "DocumentSequence",
    "DocumentStatus",
    "DocumentType",
    "Invitation",
    "Item",
    "ItemType",
    "Notification",
    "NotificationEvent",
    "NotificationPreference",
    "OutboxEvent",
    "PaymentMethod",
    "RelationType",
    "Role",
    "StoredFile",
    "User",
    "UserDevice",
    "VatRate",
    "VatType",
]
