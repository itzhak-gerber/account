"""Purchasing: suppliers, purchase orders, goods receipts and supplier invoices.

A goods receipt brings stock in at its cost (updating the weighted average) and is never
changed afterwards: mistakes are corrected with a stock adjustment. Supplier invoices record
what the supplier billed (net, VAT, total) and whether it was paid.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class OrderStatus(enum.StrEnum):
    OPEN = "open"  # ordered, nothing received yet (lines can still be edited)
    PARTIAL = "partial"  # some goods received
    RECEIVED = "received"  # everything received
    CANCELLED = "cancelled"


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Supplier(IdMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_business_name", "business_id", "name"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(20), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    address_street: Mapped[str] = mapped_column(String(200), default="")
    address_city: Mapped[str] = mapped_column(String(100), default="")
    address_zip: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(default=False)


class PurchaseOrder(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("business_id", "number", name="uq_purchase_orders_number"),
        CheckConstraint(f"status IN ({_in(OrderStatus)})", name="status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    number: Mapped[int]
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[OrderStatus] = mapped_column(String(10), default=OrderStatus.OPEN)
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    supplier: Mapped[Supplier] = relationship(lazy="joined", innerjoin=True)
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="PurchaseOrderLine.position"
    )

    @property
    def total(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0"))


class PurchaseOrderLine(IdMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint("received_quantity >= 0", name="received_non_negative"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id"))
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # before VAT
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"))


class GoodsReceipt(IdMixin, Base):
    """Goods that arrived (קליטת סחורה). Never updated or deleted."""

    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("business_id", "number", name="uq_goods_receipts_number"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    number: Mapped[int]
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id"), index=True
    )
    receipt_date: Mapped[date] = mapped_column(Date)
    # The supplier's delivery note number, as printed on their paper.
    supplier_reference: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supplier: Mapped[Supplier] = relationship(lazy="joined", innerjoin=True)
    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        lazy="selectin", order_by="GoodsReceiptLine.position"
    )

    @property
    def total(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0"))


class GoodsReceiptLine(IdMixin, Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goods_receipts.id"), index=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"))
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_order_lines.id"))
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"))


class SupplierInvoice(IdMixin, TimestampMixin, Base):
    """An invoice received from a supplier (a purchase expense, with input VAT)."""

    __tablename__ = "supplier_invoices"
    __table_args__ = (
        # The same supplier invoice cannot be entered twice.
        UniqueConstraint(
            "business_id", "supplier_id", "invoice_number", name="uq_supplier_invoices_number"
        ),
        CheckConstraint("net_amount >= 0 AND vat_amount >= 0", name="amounts_non_negative"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"))
    invoice_number: Mapped[str] = mapped_column(String(50))
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    supplier: Mapped[Supplier] = relationship(lazy="joined", innerjoin=True)

    @property
    def total(self) -> Decimal:
        return self.net_amount + self.vat_amount
