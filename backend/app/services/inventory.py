"""Stock of tracked products: levels, the movement ledger, weighted average cost, counts,
low-stock alerts, and the stock effect of issued documents.

- Tax invoices, invoice-receipts and delivery notes take goods out; credit notes bring them
  back (unless the credit is for price only). A sales kit moves its components.
- An invoice that bills delivery notes takes out only what goes beyond what those notes
  already delivered (normally nothing).
- Selling below zero is allowed (invoicing must never get stuck); the editor warns first.
- Valuation: weighted moving average. Goods in at a cost update the average; goods out leave
  at the current average, recorded on the movement.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.errors import AppError, NotFound
from app.models import (
    Document,
    DocumentRelation,
    DocumentType,
    Item,
    ItemType,
    MovementKind,
    RelationType,
    StockLevel,
    StockMovement,
)
from app.services import audit, events
from app.services.permissions import Permission, require

ZERO = Decimal("0")
OUT_DOCUMENTS = frozenset(
    {DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT, DocumentType.DELIVERY_NOTE}
)
Key = tuple[uuid.UUID, uuid.UUID | None]  # (product, kit it was sold in)


class InvalidStock(AppError):
    code = "invalid_stock"


def _cost(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def _lock_level(
    session: AsyncSession, business_id: uuid.UUID, item_id: uuid.UUID
) -> StockLevel:
    await session.execute(
        insert(StockLevel)
        .values(business_id=business_id, item_id=item_id, quantity=ZERO, average_cost=ZERO)
        .on_conflict_do_nothing()
    )
    level = await session.scalar(
        select(StockLevel)
        .where(StockLevel.business_id == business_id, StockLevel.item_id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert level is not None
    return level


async def move(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    item: Item,
    quantity: Decimal,
    kind: MovementKind,
    user_id: uuid.UUID | None,
    unit_cost: Decimal | None = None,
    document_id: uuid.UUID | None = None,
    goods_receipt_id: uuid.UUID | None = None,
    kit_item_id: uuid.UUID | None = None,
    reason: str = "",
) -> StockMovement:
    """Change one product's stock by ``quantity`` (+ in, - out) and record it."""
    level = await _lock_level(session, business_id, item.id)
    before = level.quantity
    after = before + quantity
    if quantity > 0 and unit_cost is not None:
        # Goods in at a known cost update the average (over what is actually on hand).
        on_hand = max(before, ZERO)
        level.average_cost = _cost(
            (on_hand * level.average_cost + quantity * unit_cost) / (on_hand + quantity)
        )
    cost = level.average_cost if unit_cost is None or quantity < 0 else _cost(unit_cost)
    level.quantity = after
    movement = StockMovement(
        id=uuid.uuid4(),
        business_id=business_id,
        item_id=item.id,
        kind=kind,
        quantity=quantity,
        unit_cost=cost,
        balance_after=after,
        document_id=document_id,
        goods_receipt_id=goods_receipt_id,
        kit_item_id=kit_item_id,
        reason=reason[:300],
        created_by_user_id=user_id,
    )
    session.add(movement)
    if item.min_stock is not None and before >= item.min_stock > after:
        events.emit(
            session,
            business_id,
            "item.low_stock",
            {
                "item_id": str(item.id),
                "name": item.name,
                "quantity": str(after.normalize()),
                "min_stock": str(item.min_stock.normalize()),
                "movement_id": str(movement.id),
            },
        )
    return movement


async def _quantities(
    session: AsyncSession, ctx: BusinessContext, documents: list[Document]
) -> dict[Key, Decimal]:
    """Stock quantities on these documents' lines, kits broken into their components."""
    ids = {line.item_id for d in documents for line in d.lines if line.item_id}
    if not ids:
        return {}
    items = {
        i.id: i
        for i in await session.scalars(
            select(Item).where(Item.business_id == ctx.business_id, Item.id.in_(ids))
        )
    }
    # (product, kit) -> quantity, so a product sold alone and inside a kit stay distinct.
    totals: dict[Key, Decimal] = defaultdict(lambda: ZERO)
    for line in (line for d in documents for line in d.lines):
        item = items.get(line.item_id) if line.item_id else None
        if item is None:
            continue
        if item.item_type == ItemType.KIT:
            for component in item.components:
                totals[(component.component_item_id, item.id)] += component.quantity * line.quantity
        elif item.track_inventory:
            totals[(item.id, None)] += line.quantity
    return dict(totals)


async def _billed_delivery_notes(session: AsyncSession, invoice: Document) -> list[Document]:
    return list(
        await session.scalars(
            select(Document)
            .join(DocumentRelation, DocumentRelation.to_document_id == Document.id)
            .where(
                DocumentRelation.from_document_id == invoice.id,
                DocumentRelation.relation == RelationType.CONVERTED_FROM,
                Document.type == DocumentType.DELIVERY_NOTE,
            )
        )
    )


async def apply_document(
    session: AsyncSession, ctx: BusinessContext, document: Document
) -> list[StockMovement]:
    """The stock effect of a document being issued (none for most types)."""
    if document.type in OUT_DOCUMENTS:
        sign, kind = Decimal(-1), MovementKind.SALE
    elif document.type == DocumentType.CREDIT_NOTE and document.returns_stock:
        sign, kind = Decimal(1), MovementKind.RETURN
    else:
        return []
    totals = await _quantities(session, ctx, [document])
    if document.type != DocumentType.DELIVERY_NOTE and sign < 0:
        delivered = await _quantities(session, ctx, await _billed_delivery_notes(session, document))
        totals = {k: q - delivered.get(k, ZERO) for k, q in totals.items()}
        totals = {k: q for k, q in totals.items() if q > ZERO}
    if not totals:
        return []
    parts = {
        i.id: i
        for i in await session.scalars(
            select(Item).where(
                Item.business_id == ctx.business_id,
                Item.id.in_({product for product, _ in totals}),
                Item.track_inventory.is_(True),
            )
        )
    }
    movements = []
    # Lock rows in a fixed order so concurrent documents cannot deadlock.
    for (product_id, kit_id), quantity in sorted(totals.items(), key=lambda kv: str(kv[0])):
        product = parts.get(product_id)
        if product is None:
            continue  # a kit component that is not stock-tracked
        movements.append(
            await move(
                session,
                business_id=ctx.business_id,
                item=product,
                quantity=sign * quantity,
                kind=kind,
                user_id=ctx.principal.user_id,
                document_id=document.id,
                kit_item_id=kit_id,
            )
        )
    return movements


async def adjust(
    session: AsyncSession,
    ctx: BusinessContext,
    item_id: uuid.UUID,
    *,
    counted: Decimal | None,
    change: Decimal | None,
    unit_cost: Decimal | None,
    reason: str,
) -> StockMovement:
    """A stock count (``counted``: the quantity on the shelf) or a correction (``change``)."""
    require(ctx.role, Permission.MANAGE_CATALOG)
    item = await session.get(Item, item_id)
    if item is None or item.business_id != ctx.business_id:
        raise NotFound("Item not found", code="item_not_found")
    if not item.track_inventory:
        raise InvalidStock("Stock is not tracked for this item", code="stock_not_tracked")
    if (counted is None) == (change is None):
        raise InvalidStock("Give a counted quantity or a change", code="adjustment_needs_quantity")
    if counted is not None:
        level = await _lock_level(session, ctx.business_id, item.id)
        change = counted - level.quantity
    assert change is not None
    if change == ZERO:
        raise InvalidStock("Nothing to change", code="adjustment_no_change")
    movement = await move(
        session,
        business_id=ctx.business_id,
        item=item,
        quantity=change,
        kind=MovementKind.ADJUSTMENT,
        user_id=ctx.principal.user_id,
        unit_cost=unit_cost,
        reason=reason,
    )
    await audit.record(
        session,
        ctx.principal,
        action="stock.adjusted",
        entity_type="item",
        entity_id=item.id,
        business_id=ctx.business_id,
        changes={"change": str(change), "reason": reason, "balance": str(movement.balance_after)},
    )
    return movement


@dataclass
class StockRow:
    item: Item
    quantity: Decimal
    average_cost: Decimal

    @property
    def value(self) -> Decimal:
        return (max(self.quantity, ZERO) * self.average_cost).quantize(Decimal("0.01"))

    @property
    def low(self) -> bool:
        return self.item.min_stock is not None and self.quantity < self.item.min_stock


async def _tracked_and_kits(session: AsyncSession, business_id: uuid.UUID) -> list[Item]:
    return list(
        await session.scalars(
            select(Item)
            .where(
                Item.business_id == business_id,
                Item.is_archived.is_(False),
                (Item.track_inventory.is_(True)) | (Item.item_type == ItemType.KIT),
            )
            .order_by(Item.name)
        )
    )


async def _rows(session: AsyncSession, business_id: uuid.UUID, items: list[Item]) -> list[StockRow]:
    levels = {
        level.item_id: level
        for level in await session.scalars(
            select(StockLevel).where(StockLevel.business_id == business_id)
        )
    }
    return [
        StockRow(
            item=i,
            quantity=levels[i.id].quantity if i.id in levels else ZERO,
            average_cost=levels[i.id].average_cost if i.id in levels else ZERO,
        )
        for i in items
        if i.track_inventory
    ]


async def stock_rows(session: AsyncSession, business_id: uuid.UUID) -> list[StockRow]:
    """Stock-tracked products of the business in the current security context (exports)."""
    return await _rows(session, business_id, await _tracked_and_kits(session, business_id))


async def stock(session: AsyncSession, ctx: BusinessContext) -> dict[str, Any]:
    """Every stock-tracked product with its level and value, and every kit with how many can
    be put together from what is on hand."""
    require(ctx.role, Permission.VIEW_CATALOG)
    items = await _tracked_and_kits(session, ctx.business_id)
    rows = await _rows(session, ctx.business_id, items)
    by_id = {r.item.id: r for r in rows}
    kits = []
    for kit in (i for i in items if i.item_type == ItemType.KIT):
        tracked = [c for c in kit.components if c.component_item_id in by_id]
        available = (
            min(
                (max(by_id[c.component_item_id].quantity, ZERO) / c.quantity).to_integral_value(
                    rounding="ROUND_FLOOR"
                )
                for c in tracked
            )
            if tracked
            else None
        )
        kits.append({"item": kit, "available": available})
    return {
        "items": rows,
        "kits": kits,
        "total_value": sum((r.value for r in rows), ZERO),
    }


async def movements(
    session: AsyncSession, ctx: BusinessContext, item_id: uuid.UUID, limit: int = 100
) -> list[StockMovement]:
    require(ctx.role, Permission.VIEW_CATALOG)
    return list(
        await session.scalars(
            select(StockMovement)
            .where(StockMovement.business_id == ctx.business_id, StockMovement.item_id == item_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(min(limit, 500))
        )
    )
