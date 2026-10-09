import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.schemas.catalog import ItemOut
from app.schemas.inventory import AdjustmentIn, KitOut, MovementOut, StockItemOut, StockOut
from app.services import inventory

router = APIRouter(prefix="/businesses/{business_id}/inventory", tags=["inventory"])


@router.get("")
async def stock(ctx: CurrentBusiness, session: DbSession) -> StockOut:
    """Stock-tracked products with quantity, average cost and value; kits with availability."""
    data = await inventory.stock(session, ctx)
    return StockOut(
        items=[
            StockItemOut(
                item=ItemOut.model_validate(r.item),
                quantity=r.quantity,
                average_cost=r.average_cost,
                value=r.value,
                low=r.low,
            )
            for r in data["items"]
        ],
        kits=[
            KitOut(item=ItemOut.model_validate(k["item"]), available=k["available"])
            for k in data["kits"]
        ],
        total_value=data["total_value"],
    )


@router.get("/{item_id}/movements")
async def movements(
    item_id: uuid.UUID,
    ctx: CurrentBusiness,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MovementOut]:
    rows = await inventory.movements(session, ctx, item_id, limit)
    return [MovementOut.model_validate(m) for m in rows]


@router.post("/{item_id}/adjustments", status_code=status.HTTP_201_CREATED)
async def adjust(
    item_id: uuid.UUID, data: AdjustmentIn, ctx: CurrentBusiness, session: DbSession
) -> MovementOut:
    """Record a stock count (``counted``) or a correction (``change``), with a reason."""
    movement = await inventory.adjust(
        session,
        ctx,
        item_id,
        counted=data.counted,
        change=data.change,
        unit_cost=data.unit_cost,
        reason=data.reason,
    )
    await commit(session)
    return MovementOut.model_validate(movement)
