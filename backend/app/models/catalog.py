"""Customers and the product/service catalog of a business."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class ItemType(enum.StrEnum):
    PRODUCT = "product"
    SERVICE = "service"
    # A sales kit: sold as one line, made of other items (see ItemComponent). Selling it takes
    # its components out of stock; the kit itself has no stock.
    KIT = "kit"


class VatType(enum.StrEnum):
    STANDARD = "standard"  # the current VAT rate
    EXEMPT = "exempt"  # פטור
    ZERO = "zero"  # מע"מ אפס (e.g. export of services)


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Customer(IdMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_business_name", "business_id", "name"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    address_street: Mapped[str] = mapped_column(String(200), default="")
    address_city: Mapped[str] = mapped_column(String(100), default="")
    address_zip: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(default=False)


class Item(IdMixin, TimestampMixin, Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_business_name", "business_id", "name"),
        CheckConstraint(f"item_type IN ({_in(ItemType)})", name="item_type"),
        CheckConstraint(f"vat_type IN ({_in(VatType)})", name="vat_type"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    item_type: Mapped[ItemType] = mapped_column(String(10), default=ItemType.SERVICE)
    sku: Mapped[str] = mapped_column(String(64), default="")
    barcode: Mapped[str] = mapped_column(String(64), default="")
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="")
    # Price before VAT, in the business's currency.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    vat_type: Mapped[VatType] = mapped_column(String(10), default=VatType.STANDARD)
    # Products only: keep stock levels and movements (services and kits never do).
    track_inventory: Mapped[bool] = mapped_column(default=False)
    # Alert when stock falls below this (None: no alert).
    min_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    is_archived: Mapped[bool] = mapped_column(default=False)

    components: Mapped[list["ItemComponent"]] = relationship(
        foreign_keys="ItemComponent.kit_item_id",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ItemComponent.position",
    )


class ItemComponent(Base):
    """One component of a sales kit: ``quantity`` of ``component_item_id`` per kit."""

    __tablename__ = "item_components"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    kit_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    component_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), primary_key=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
