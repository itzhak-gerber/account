"""Stock: the current level of each tracked product, and an append-only ledger of movements.

Valuation is by weighted (moving) average cost: goods coming in at a cost update the average;
goods going out leave at the current average, which is recorded on the movement.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class MovementKind(enum.StrEnum):
    SALE = "sale"  # a tax invoice or invoice-receipt was issued
    RETURN = "return"  # a credit note returned the goods
    ADJUSTMENT = "adjustment"  # a stock count or a manual correction
    RECEIPT = "receipt"  # goods received from a supplier


class StockLevel(Base):
    """Current quantity and average cost of one product. Row-locked while moving stock."""

    __tablename__ = "stock_levels"

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockMovement(IdMixin, Base):
    """One change in stock. Never updated or deleted (the database only allows inserts)."""

    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_movements_item", "business_id", "item_id", "created_at"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    kind: Mapped[MovementKind] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # + in, - out
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("goods_receipts.id"))
    # The kit sold, when this movement is one of its components.
    kit_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id"))
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
