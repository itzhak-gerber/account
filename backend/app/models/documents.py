"""Documents (quotes, invoices, receipts, credit notes), their lines, payments and numbering."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.catalog import VatType, _in


class DocumentType(enum.StrEnum):
    QUOTE = "quote"  # הצעת מחיר
    PROFORMA_INVOICE = "proforma_invoice"  # חשבון עסקה
    TAX_INVOICE = "tax_invoice"  # חשבונית מס
    RECEIPT = "receipt"  # קבלה
    TAX_INVOICE_RECEIPT = "tax_invoice_receipt"  # חשבונית מס/קבלה
    CREDIT_NOTE = "credit_note"  # חשבונית מס זיכוי


class DocumentStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CHECK = "check"
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    DIGITAL_WALLET = "digital_wallet"  # e.g. Bit, PayBox
    OTHER = "other"


class RelationType(enum.StrEnum):
    CONVERTED_FROM = "converted_from"  # e.g. invoice created from a quote
    CREDITS = "credits"  # credit note → the invoice it credits
    PAYS = "pays"  # receipt → invoice (M4)


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("business_id", "type", "number"),
        Index("ix_documents_business_type_status", "business_id", "type", "status"),
        Index("ix_documents_business_issue_date", "business_id", "issue_date"),
        CheckConstraint(f"type IN ({_in(DocumentType)})", name="type"),
        CheckConstraint(f"status IN ({_in(DocumentStatus)})", name="status"),
        CheckConstraint(
            "(status = 'draft' AND number IS NULL) OR (status = 'issued' AND number IS NOT NULL)",
            name="number_iff_issued",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[DocumentType] = mapped_column(String(30))
    status: Mapped[DocumentStatus] = mapped_column(String(10), default=DocumentStatus.DRAFT)
    number: Mapped[int | None] = mapped_column(Integer)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    # Customer details as printed on the document (frozen once issued).
    customer: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # The business's details at the moment of issue.
    business_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    currency: Mapped[str] = mapped_column(String(3), default="ILS")
    prices_include_vat: Mapped[bool] = mapped_column(default=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    # Updated after issue: receipts paying this invoice, and credit notes against it.
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    amount_credited: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    # A proforma (חשבון עסקה) is closed once a tax invoice made from it is issued.
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT")
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    allocation_number: Mapped[str | None] = mapped_column(String(20))
    # Credit notes: whether the goods come back into stock (False for a price-only credit).
    returns_stock: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    original_pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id"))
    original_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(10), default="web")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["DocumentLine"]] = relationship(
        order_by="DocumentLine.position", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["DocumentPayment"]] = relationship(
        order_by="DocumentPayment.position", cascade="all, delete-orphan", lazy="selectin"
    )


class DocumentLine(IdMixin, Base):
    __tablename__ = "document_lines"
    __table_args__ = (
        CheckConstraint(f"vat_type IN ({_in(VatType)})", name="vat_type"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="discount_range"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="")
    # As entered: before VAT, or including VAT when the document's prices_include_vat is set.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    vat_type: Mapped[VatType] = mapped_column(String(10), default=VatType.STANDARD)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class DocumentPayment(IdMixin, Base):
    __tablename__ = "document_payments"
    __table_args__ = (
        CheckConstraint(f"method IN ({_in(PaymentMethod)})", name="method"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    method: Mapped[PaymentMethod] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_date: Mapped[date] = mapped_column(Date)
    # Method-specific details: bank/branch/account, check number, card last digits, etc.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class DocumentRelation(IdMixin, Base):
    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint("from_document_id", "to_document_id", "relation"),
        CheckConstraint(f"relation IN ({_in(RelationType)})", name="relation"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    from_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    to_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )
    relation: Mapped[RelationType] = mapped_column(String(20))
    # For "pays": the part of the receipt applied to that invoice.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentSequence(Base):
    """Next number per business and document type. Row-locked while issuing (gapless)."""

    __tablename__ = "document_sequences"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    document_type: Mapped[DocumentType] = mapped_column(String(30), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)


class VatRate(IdMixin, Base):
    """Israeli VAT rate by effective date (not tenant data)."""

    __tablename__ = "vat_rates"

    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    effective_from: Mapped[date] = mapped_column(Date, unique=True)


class StoredFile(IdMixin, Base):
    __tablename__ = "files"

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(IdMixin, Base):
    """Domain events written in the same transaction as the change (dispatched later, M5)."""

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_pending", "status", "available_at"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryStatus(enum.StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class DocumentDelivery(IdMixin, Base):
    """A document emailed to a customer (one row per send, with its outcome)."""

    __tablename__ = "document_deliveries"
    __table_args__ = (CheckConstraint(f"status IN ({_in(DeliveryStatus)})", name="status"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )
    recipients: Mapped[list[str]] = mapped_column(JSONB)
    subject: Mapped[str] = mapped_column(String(300))
    variant: Mapped[str] = mapped_column(String(10))  # original | copy
    status: Mapped[DeliveryStatus] = mapped_column(String(10), default=DeliveryStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(String(500))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExportStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class DataExport(IdMixin, Base):
    """A full export of one business's data (documents as PDF copies, spreadsheets, and the
    tax authority's uniform-format file), built in the background as one ZIP file."""

    __tablename__ = "data_exports"

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ExportStatus] = mapped_column(String(10), default=ExportStatus.PENDING)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    size: Mapped[int | None] = mapped_column(Integer)
    documents: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
