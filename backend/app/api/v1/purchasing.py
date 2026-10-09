import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.models import OrderStatus
from app.schemas.purchasing import (
    OrderIn,
    OrderOut,
    OrderPatch,
    ReceiptIn,
    ReceiptOut,
    SupplierIn,
    SupplierInvoiceIn,
    SupplierInvoiceOut,
    SupplierInvoicePatch,
    SupplierOut,
    SupplierPatch,
)
from app.services import purchasing

router = APIRouter(prefix="/businesses/{business_id}", tags=["purchasing"])
Limit = Annotated[int, Query(ge=1, le=500)]


# --- suppliers -------------------------------------------------------------------------


@router.get("/suppliers")
async def list_suppliers(
    ctx: CurrentBusiness,
    session: DbSession,
    q: str | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SupplierOut]:
    rows = await purchasing.list_suppliers(
        session, ctx, q=q, include_archived=include_archived, limit=limit, offset=offset
    )
    return [SupplierOut.model_validate(s) for s in rows]


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(
    ctx: CurrentBusiness, data: SupplierIn, session: DbSession
) -> SupplierOut:
    out = SupplierOut.model_validate(await purchasing.create_supplier(session, ctx, data))
    await commit(session)
    return out


@router.get("/suppliers/{supplier_id}")
async def get_supplier(
    ctx: CurrentBusiness, supplier_id: uuid.UUID, session: DbSession
) -> SupplierOut:
    return SupplierOut.model_validate(await purchasing.get_supplier(session, ctx, supplier_id))


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(
    ctx: CurrentBusiness, supplier_id: uuid.UUID, patch: SupplierPatch, session: DbSession
) -> SupplierOut:
    out = SupplierOut.model_validate(
        await purchasing.update_supplier(session, ctx, supplier_id, patch)
    )
    await commit(session)
    return out


# --- purchase orders -------------------------------------------------------------------


@router.get("/purchase-orders")
async def list_orders(
    ctx: CurrentBusiness,
    session: DbSession,
    status: OrderStatus | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: Limit = 100,
) -> list[OrderOut]:
    rows = await purchasing.list_orders(
        session, ctx, status=status, supplier_id=supplier_id, limit=limit
    )
    return [OrderOut.model_validate(o) for o in rows]


@router.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
async def create_order(ctx: CurrentBusiness, data: OrderIn, session: DbSession) -> OrderOut:
    out = OrderOut.model_validate(await purchasing.create_order(session, ctx, data))
    await commit(session)
    return out


@router.get("/purchase-orders/{order_id}")
async def get_order(ctx: CurrentBusiness, order_id: uuid.UUID, session: DbSession) -> OrderOut:
    return OrderOut.model_validate(await purchasing.get_order(session, ctx, order_id))


@router.patch("/purchase-orders/{order_id}")
async def update_order(
    ctx: CurrentBusiness, order_id: uuid.UUID, patch: OrderPatch, session: DbSession
) -> OrderOut:
    out = OrderOut.model_validate(await purchasing.update_order(session, ctx, order_id, patch))
    await commit(session)
    return out


@router.post("/purchase-orders/{order_id}/cancel")
async def cancel_order(ctx: CurrentBusiness, order_id: uuid.UUID, session: DbSession) -> OrderOut:
    out = OrderOut.model_validate(await purchasing.cancel_order(session, ctx, order_id))
    await commit(session)
    return out


# --- goods receipts --------------------------------------------------------------------


@router.get("/goods-receipts")
async def list_receipts(
    ctx: CurrentBusiness,
    session: DbSession,
    purchase_order_id: uuid.UUID | None = None,
    limit: Limit = 100,
) -> list[ReceiptOut]:
    rows = await purchasing.list_receipts(
        session, ctx, purchase_order_id=purchase_order_id, limit=limit
    )
    return [ReceiptOut.model_validate(r) for r in rows]


@router.post("/goods-receipts", status_code=status.HTTP_201_CREATED)
async def create_receipt(ctx: CurrentBusiness, data: ReceiptIn, session: DbSession) -> ReceiptOut:
    """Goods arrived: stock goes up at the given cost, and the order (if any) is updated."""
    out = ReceiptOut.model_validate(await purchasing.create_receipt(session, ctx, data))
    await commit(session)
    return out


@router.get("/goods-receipts/{receipt_id}")
async def get_receipt(
    ctx: CurrentBusiness, receipt_id: uuid.UUID, session: DbSession
) -> ReceiptOut:
    return ReceiptOut.model_validate(await purchasing.get_receipt(session, ctx, receipt_id))


# --- supplier invoices -----------------------------------------------------------------


@router.get("/supplier-invoices")
async def list_invoices(
    ctx: CurrentBusiness,
    session: DbSession,
    unpaid: bool | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: Limit = 200,
) -> list[SupplierInvoiceOut]:
    rows = await purchasing.list_invoices(
        session, ctx, unpaid=unpaid, supplier_id=supplier_id, limit=limit
    )
    return [SupplierInvoiceOut.model_validate(i) for i in rows]


@router.post("/supplier-invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    ctx: CurrentBusiness, data: SupplierInvoiceIn, session: DbSession
) -> SupplierInvoiceOut:
    out = SupplierInvoiceOut.model_validate(await purchasing.create_invoice(session, ctx, data))
    await commit(session)
    return out


@router.get("/supplier-invoices/{invoice_id}")
async def get_invoice(
    ctx: CurrentBusiness, invoice_id: uuid.UUID, session: DbSession
) -> SupplierInvoiceOut:
    return SupplierInvoiceOut.model_validate(await purchasing.get_invoice(session, ctx, invoice_id))


@router.patch("/supplier-invoices/{invoice_id}")
async def update_invoice(
    ctx: CurrentBusiness, invoice_id: uuid.UUID, patch: SupplierInvoicePatch, session: DbSession
) -> SupplierInvoiceOut:
    out = SupplierInvoiceOut.model_validate(
        await purchasing.update_invoice(session, ctx, invoice_id, patch)
    )
    await commit(session)
    return out


@router.delete("/supplier-invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(ctx: CurrentBusiness, invoice_id: uuid.UUID, session: DbSession) -> None:
    await purchasing.delete_invoice(session, ctx, invoice_id)
    await commit(session)
