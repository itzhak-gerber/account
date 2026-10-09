"""SQLAlchemy models. Import every model module here so Alembic sees it."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.catalog import Customer, Item, ItemType, VatType
from app.models.documents import (
    DataExport,
    DeliveryStatus,
    Document,
    DocumentDelivery,
    DocumentLine,
    DocumentPayment,
    DocumentRelation,
    DocumentSequence,
    DocumentStatus,
    DocumentType,
    ExportStatus,
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
    PushSubscription,
    UserDevice,
)

__all__ = [
    "AuditLog",
    "Base",
    "Business",
    "BusinessMember",
    "BusinessType",
    "Customer",
    "DataExport",
    "DeliveryStatus",
    "Document",
    "DocumentDelivery",
    "DocumentLine",
    "DocumentPayment",
    "DocumentRelation",
    "DocumentSequence",
    "DocumentStatus",
    "DocumentType",
    "ExportStatus",
    "Invitation",
    "Item",
    "ItemType",
    "Notification",
    "NotificationEvent",
    "NotificationPreference",
    "OutboxEvent",
    "PaymentMethod",
    "PushSubscription",
    "RelationType",
    "Role",
    "StoredFile",
    "User",
    "UserDevice",
    "VatRate",
    "VatType",
]
