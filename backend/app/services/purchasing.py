"""Purchasing: suppliers, purchase orders, goods receipts and supplier invoices.

- A purchase order lists what was ordered; it can be edited until goods start arriving.
- A goods receipt brings stock in at its cost (updating the weighted average) and marks the
  order's lines as received. Receipts are never changed: a mistake is corrected with a stock
  adjustment.
- A supplier invoice records what the supplier billed and whether it was paid. Its amounts do
  not change stock costs (the receipt's cost does).
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.errors import AppError, Conflict, NotFound
from app.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Item,
    ItemType,
    MovementKind,
    OrderStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierInvoice,
)
from app.schemas.purchasing import (
    OrderIn,
    OrderLineIn,
    OrderPatch,
    ReceiptIn,
    SupplierIn,
    SupplierInvoiceIn,
    SupplierInvoicePatch,
    SupplierPatch,
)
from app.services import audit, inventory
from app.services.permissions import Permission, require

ZERO = Decimal("0")


class InvalidPurchase(AppError):
    code = "invalid_purchase"


async def _next_number(
    session: AsyncSession, business_id: uuid.UUID, model: type[PurchaseOrder] | type[GoodsReceipt]
) -> int:
    # One numbering per business and kind; the lock serialises concurrent creations.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{model.__tablename__}:{business_id}"},
    )
    last = await session.scalar(
        select(func.max(model.number)).where(model.business_id == business_id)
    )
    return (last or 0) + 1


async def _items(
    session: AsyncSession, ctx: BusinessContext, ids: set[uuid.UUID]
) -> dict[uuid.UUID, Item]:
    if not ids:
        return {}
    found = {
        i.id: i
        for i in await session.scalars(
            select(Item).where(Item.business_id == ctx.business_id, Item.id.in_(ids))
        )
    }
    if len(found) != len(ids):
        raise NotFound("Item not found", code="item_not_found")
    return found


# --- suppliers -------------------------------------------------------------------------


async def list_suppliers(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    q: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Supplier]:
    require(ctx.role, Permission.VIEW_PURCHASING)
    query = select(Supplier).where(Supplier.business_id == ctx.business_id)
    if not include_archived:
        query = query.where(Supplier.is_archived.is_(False))
    if q:
        pattern = f"%{q.strip().replace('%', '').replace('_', '')}%"
        query = query.where(
            or_(
                Supplier.name.ilike(pattern),
                Supplier.tax_id.ilike(pattern),
                Supplier.contact_name.ilike(pattern),
                Supplier.phone.ilike(pattern),
            )
        )
    return list(await session.scalars(query.order_by(Supplier.name).limit(limit).offset(offset)))


async def get_supplier(
    session: AsyncSession, ctx: BusinessContext, supplier_id: uuid.UUID
) -> Supplier:
    require(ctx.role, Permission.VIEW_PURCHASING)
    supplier = await session.get(Supplier, supplier_id)
    if supplier is None or supplier.business_id != ctx.business_id:
        raise NotFound("Supplier not found", code="supplier_not_found")
    return supplier


async def create_supplier(
    session: AsyncSession, ctx: BusinessContext, data: SupplierIn
) -> Supplier:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    values = data.model_dump()
    values["email"] = values["email"] or ""
    supplier = Supplier(business_id=ctx.business_id, is_archived=False, **values)
    session.add(supplier)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="supplier.created",
        entity_type="supplier",
        entity_id=supplier.id,
        business_id=ctx.business_id,
        changes={"name": supplier.name},
    )
    return supplier


async def update_supplier(
    session: AsyncSession, ctx: BusinessContext, supplier_id: uuid.UUID, patch: SupplierPatch
) -> Supplier:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    supplier = await get_supplier(session, ctx, supplier_id)
    changes: dict[str, dict[str, str]] = {}
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is None and field != "email":
            continue
        value = "" if value is None else value
        if getattr(supplier, field) != value:
            changes[field] = {"from": str(getattr(supplier, field)), "to": str(value)}
            setattr(supplier, field, value)
    if changes:
        await session.flush()
        await session.refresh(supplier)
        await audit.record(
            session,
            ctx.principal,
            action="supplier.updated",
            entity_type="supplier",
            entity_id=supplier.id,
            business_id=ctx.business_id,
            changes=changes,
        )
    return supplier


# --- purchase orders -------------------------------------------------------------------


async def _order_lines(
    session: AsyncSession, ctx: BusinessContext, lines: list[OrderLineIn]
) -> list[PurchaseOrderLine]:
    items = await _items(session, ctx, {line.item_id for line in lines if line.item_id})
    if any(i.item_type == ItemType.KIT for i in items.values()):
        raise InvalidPurchase("Order the kit's components, not the kit", code="purchase_kit")
    return [
        PurchaseOrderLine(
            id=uuid.uuid4(),
            business_id=ctx.business_id,
            position=n,
            item_id=line.item_id,
            description=line.description,
            quantity=line.quantity,
            unit_cost=line.unit_cost,
            received_quantity=ZERO,
        )
        for n, line in enumerate(lines)
    ]


async def list_orders(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    status: OrderStatus | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[PurchaseOrder]:
    require(ctx.role, Permission.VIEW_PURCHASING)
    query = select(PurchaseOrder).where(PurchaseOrder.business_id == ctx.business_id)
    if status:
        query = query.where(PurchaseOrder.status == status)
    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    return list(await session.scalars(query.order_by(PurchaseOrder.number.desc()).limit(limit)))


async def get_order(
    session: AsyncSession, ctx: BusinessContext, order_id: uuid.UUID, *, lock: bool = False
) -> PurchaseOrder:
    require(ctx.role, Permission.VIEW_PURCHASING)
    query = select(PurchaseOrder).where(
        PurchaseOrder.id == order_id, PurchaseOrder.business_id == ctx.business_id
    )
    if lock:
        query = query.with_for_update(of=PurchaseOrder).execution_options(populate_existing=True)
    order = await session.scalar(query)
    if order is None:
        raise NotFound("Purchase order not found", code="purchase_order_not_found")
    return order


async def create_order(session: AsyncSession, ctx: BusinessContext, data: OrderIn) -> PurchaseOrder:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    supplier = await get_supplier(session, ctx, data.supplier_id)
    order = PurchaseOrder(
        id=uuid.uuid4(),
        business_id=ctx.business_id,
        number=await _next_number(session, ctx.business_id, PurchaseOrder),
        supplier_id=supplier.id,
        status=OrderStatus.OPEN,
        order_date=data.order_date,
        expected_date=data.expected_date,
        notes=data.notes,
        created_by_user_id=ctx.principal.user_id,
        lines=await _order_lines(session, ctx, data.lines),
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    await audit.record(
        session,
        ctx.principal,
        action="purchase_order.created",
        entity_type="purchase_order",
        entity_id=order.id,
        business_id=ctx.business_id,
        changes={"number": order.number, "supplier": supplier.name, "total": str(order.total)},
    )
    return order


async def update_order(
    session: AsyncSession, ctx: BusinessContext, order_id: uuid.UUID, patch: OrderPatch
) -> PurchaseOrder:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    order = await get_order(session, ctx, order_id, lock=True)
    if order.status != OrderStatus.OPEN:
        raise InvalidPurchase(
            "Only an order with nothing received can be edited", code="purchase_order_locked"
        )
    values = patch.model_dump(exclude_unset=True, exclude={"lines"})
    if patch.supplier_id is not None:
        await get_supplier(session, ctx, patch.supplier_id)
    for field, value in values.items():
        if value is None and field != "expected_date":
            continue
        setattr(order, field, value)
    if patch.lines is not None:
        order.lines = await _order_lines(session, ctx, patch.lines)
    await session.flush()
    await session.refresh(order)
    await audit.record(
        session,
        ctx.principal,
        action="purchase_order.updated",
        entity_type="purchase_order",
        entity_id=order.id,
        business_id=ctx.business_id,
        changes={"total": str(order.total)},
    )
    return order


async def cancel_order(
    session: AsyncSession, ctx: BusinessContext, order_id: uuid.UUID
) -> PurchaseOrder:
    """Cancel what has not arrived yet (goods already received stay in stock)."""
    require(ctx.role, Permission.MANAGE_PURCHASING)
    order = await get_order(session, ctx, order_id, lock=True)
    if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIAL):
        raise InvalidPurchase("This order is already closed", code="purchase_order_closed")
    order.status = OrderStatus.CANCELLED
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="purchase_order.cancelled",
        entity_type="purchase_order",
        entity_id=order.id,
        business_id=ctx.business_id,
    )
    return order


# --- goods receipts --------------------------------------------------------------------


async def list_receipts(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    purchase_order_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[GoodsReceipt]:
    require(ctx.role, Permission.VIEW_PURCHASING)
    query = select(GoodsReceipt).where(GoodsReceipt.business_id == ctx.business_id)
    if purchase_order_id:
        query = query.where(GoodsReceipt.purchase_order_id == purchase_order_id)
    return list(await session.scalars(query.order_by(GoodsReceipt.number.desc()).limit(limit)))


async def get_receipt(
    session: AsyncSession, ctx: BusinessContext, receipt_id: uuid.UUID
) -> GoodsReceipt:
    require(ctx.role, Permission.VIEW_PURCHASING)
    receipt = await session.get(GoodsReceipt, receipt_id)
    if receipt is None or receipt.business_id != ctx.business_id:
        raise NotFound("Goods receipt not found", code="goods_receipt_not_found")
    return receipt


async def create_receipt(
    session: AsyncSession, ctx: BusinessContext, data: ReceiptIn
) -> GoodsReceipt:
    """Record goods that arrived: stock goes up at the given cost, the order is updated."""
    require(ctx.role, Permission.MANAGE_PURCHASING)
    supplier = await get_supplier(session, ctx, data.supplier_id)
    order = None
    order_lines: dict[uuid.UUID, PurchaseOrderLine] = {}
    if data.purchase_order_id:
        order = await get_order(session, ctx, data.purchase_order_id, lock=True)
        if order.supplier_id != supplier.id:
            raise InvalidPurchase("The order is from another supplier", code="receipt_supplier")
        if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIAL):
            raise InvalidPurchase("This order is already closed", code="purchase_order_closed")
        order_lines = {line.id: line for line in order.lines}
    items = await _items(session, ctx, {line.item_id for line in data.lines})
    if any(i.item_type != ItemType.PRODUCT for i in items.values()):
        raise InvalidPurchase("Only products can be received", code="receipt_not_product")
    for line in data.lines:
        if line.order_line_id is None:
            continue
        ordered = order_lines.get(line.order_line_id)
        if ordered is None or ordered.item_id != line.item_id:
            raise InvalidPurchase(
                "The line does not match the order", code="receipt_order_line_mismatch"
            )

    receipt = GoodsReceipt(
        id=uuid.uuid4(),
        business_id=ctx.business_id,
        number=await _next_number(session, ctx.business_id, GoodsReceipt),
        supplier_id=supplier.id,
        purchase_order_id=order.id if order else None,
        receipt_date=data.receipt_date,
        supplier_reference=data.supplier_reference,
        notes=data.notes,
        created_by_user_id=ctx.principal.user_id,
    )
    session.add(receipt)
    lines = [
        GoodsReceiptLine(
            id=uuid.uuid4(),
            receipt_id=receipt.id,
            business_id=ctx.business_id,
            position=n,
            item_id=line.item_id,
            order_line_id=line.order_line_id,
            description=items[line.item_id].name,
            quantity=line.quantity,
            unit_cost=line.unit_cost,
        )
        for n, line in enumerate(data.lines)
    ]
    session.add_all(lines)
    await session.flush()

    # Lock stock rows in a fixed order so concurrent receipts and sales cannot deadlock.
    for row in sorted(lines, key=lambda r: (str(r.item_id), r.position)):
        item = items[row.item_id]
        if item.track_inventory:
            await inventory.move(
                session,
                business_id=ctx.business_id,
                item=item,
                quantity=row.quantity,
                kind=MovementKind.RECEIPT,
                user_id=ctx.principal.user_id,
                unit_cost=row.unit_cost,
                goods_receipt_id=receipt.id,
                reason=f"{supplier.name} {data.supplier_reference}".strip(),
            )
        if row.order_line_id:
            order_lines[row.order_line_id].received_quantity += row.quantity
    if order is not None:
        # Only goods arrive: freight or service lines on the order do not keep it open.
        order_items = await _items(
            session, ctx, {line.item_id for line in order.lines if line.item_id}
        )
        goods = [
            line
            for line in order.lines
            if line.item_id and order_items[line.item_id].item_type == ItemType.PRODUCT
        ]
        done = all(line.received_quantity >= line.quantity for line in goods)
        order.status = OrderStatus.RECEIVED if done else OrderStatus.PARTIAL

    await session.flush()
    await session.refresh(receipt, ["lines", "supplier"])
    await audit.record(
        session,
        ctx.principal,
        action="goods_receipt.created",
        entity_type="goods_receipt",
        entity_id=receipt.id,
        business_id=ctx.business_id,
        changes={
            "number": receipt.number,
            "supplier": supplier.name,
            "purchase_order": order.number if order else None,
            "total": str(receipt.total),
        },
    )
    return receipt


# --- supplier invoices -----------------------------------------------------------------


async def list_invoices(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    unpaid: bool | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[SupplierInvoice]:
    require(ctx.role, Permission.VIEW_PURCHASING)
    query = select(SupplierInvoice).where(SupplierInvoice.business_id == ctx.business_id)
    if unpaid is not None:
        query = query.where(
            SupplierInvoice.paid_date.is_(None) if unpaid else SupplierInvoice.paid_date.isnot(None)
        )
    if supplier_id:
        query = query.where(SupplierInvoice.supplier_id == supplier_id)
    return list(
        await session.scalars(
            query.order_by(
                SupplierInvoice.invoice_date.desc(), SupplierInvoice.created_at.desc()
            ).limit(limit)
        )
    )


async def get_invoice(
    session: AsyncSession, ctx: BusinessContext, invoice_id: uuid.UUID
) -> SupplierInvoice:
    require(ctx.role, Permission.VIEW_PURCHASING)
    invoice = await session.get(SupplierInvoice, invoice_id)
    if invoice is None or invoice.business_id != ctx.business_id:
        raise NotFound("Supplier invoice not found", code="supplier_invoice_not_found")
    return invoice


async def _check_invoice(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    supplier_id: uuid.UUID,
    invoice_number: str,
    purchase_order_id: uuid.UUID | None,
    exclude: uuid.UUID | None = None,
) -> None:
    query = select(SupplierInvoice.id).where(
        SupplierInvoice.business_id == ctx.business_id,
        SupplierInvoice.supplier_id == supplier_id,
        SupplierInvoice.invoice_number == invoice_number,
    )
    if exclude:
        query = query.where(SupplierInvoice.id != exclude)
    if await session.scalar(query):
        raise Conflict(
            "This supplier invoice was already entered", code="supplier_invoice_duplicate"
        )
    if purchase_order_id:
        order = await get_order(session, ctx, purchase_order_id)
        if order.supplier_id != supplier_id:
            raise InvalidPurchase("The order is from another supplier", code="receipt_supplier")


async def create_invoice(
    session: AsyncSession, ctx: BusinessContext, data: SupplierInvoiceIn
) -> SupplierInvoice:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    supplier = await get_supplier(session, ctx, data.supplier_id)
    await _check_invoice(
        session,
        ctx,
        supplier_id=supplier.id,
        invoice_number=data.invoice_number,
        purchase_order_id=data.purchase_order_id,
    )
    invoice = SupplierInvoice(
        id=uuid.uuid4(),
        business_id=ctx.business_id,
        created_by_user_id=ctx.principal.user_id,
        **data.model_dump(),
    )
    session.add(invoice)
    await session.flush()
    await session.refresh(invoice)
    await audit.record(
        session,
        ctx.principal,
        action="supplier_invoice.created",
        entity_type="supplier_invoice",
        entity_id=invoice.id,
        business_id=ctx.business_id,
        changes={
            "supplier": supplier.name,
            "number": invoice.invoice_number,
            "total": str(invoice.total),
        },
    )
    return invoice


_NULLABLE = {"due_date", "paid_date", "purchase_order_id"}


async def update_invoice(
    session: AsyncSession,
    ctx: BusinessContext,
    invoice_id: uuid.UUID,
    patch: SupplierInvoicePatch,
) -> SupplierInvoice:
    require(ctx.role, Permission.MANAGE_PURCHASING)
    invoice = await get_invoice(session, ctx, invoice_id)
    values: dict[str, Any] = {
        k: v
        for k, v in patch.model_dump(exclude_unset=True).items()
        if v is not None or k in _NULLABLE
    }
    if "invoice_number" in values or values.get("purchase_order_id"):
        await _check_invoice(
            session,
            ctx,
            supplier_id=invoice.supplier_id,
            invoice_number=values.get("invoice_number", invoice.invoice_number),
            purchase_order_id=values.get("purchase_order_id"),
            exclude=invoice.id,
        )
    changes = {
        k: {"from": str(getattr(invoice, k)), "to": str(v)}
        for k, v in values.items()
        if getattr(invoice, k) != v
    }
    for k, v in values.items():
        setattr(invoice, k, v)
    if changes:
        await session.flush()
        await session.refresh(invoice)
        await audit.record(
            session,
            ctx.principal,
            action="supplier_invoice.updated",
            entity_type="supplier_invoice",
            entity_id=invoice.id,
            business_id=ctx.business_id,
            changes=changes,
        )
    return invoice


async def delete_invoice(
    session: AsyncSession, ctx: BusinessContext, invoice_id: uuid.UUID
) -> None:
    """Remove an invoice entered by mistake (the audit log keeps what it was)."""
    require(ctx.role, Permission.MANAGE_PURCHASING)
    invoice = await get_invoice(session, ctx, invoice_id)
    await audit.record(
        session,
        ctx.principal,
        action="supplier_invoice.deleted",
        entity_type="supplier_invoice",
        entity_id=invoice.id,
        business_id=ctx.business_id,
        changes={
            "supplier": invoice.supplier.name,
            "number": invoice.invoice_number,
            "invoice_date": str(invoice.invoice_date),
            "total": str(invoice.total),
        },
    )
    await session.delete(invoice)
    await session.flush()
