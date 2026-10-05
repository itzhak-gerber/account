import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.schemas.catalog import CustomerIn, CustomerOut, CustomerPatch, ItemIn, ItemOut, ItemPatch
from app.services import catalog

router = APIRouter(prefix="/businesses/{business_id}", tags=["catalog"])
Limit = Annotated[int, Query(ge=1, le=200)]


@router.get("/customers")
async def list_customers(
    ctx: CurrentBusiness,
    session: DbSession,
    q: str | None = None,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CustomerOut]:
    rows = await catalog.list_customers(
        session, ctx, q=q, include_archived=include_archived, limit=limit, offset=offset
    )
    return [CustomerOut.model_validate(c) for c in rows]


@router.post("/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    ctx: CurrentBusiness, data: CustomerIn, session: DbSession
) -> CustomerOut:
    out = CustomerOut.model_validate(await catalog.create_customer(session, ctx, data))
    await commit(session)
    return out


@router.get("/customers/{customer_id}")
async def get_customer(
    ctx: CurrentBusiness, customer_id: uuid.UUID, session: DbSession
) -> CustomerOut:
    return CustomerOut.model_validate(await catalog.get_customer(session, ctx, customer_id))


@router.patch("/customers/{customer_id}")
async def update_customer(
    ctx: CurrentBusiness, customer_id: uuid.UUID, patch: CustomerPatch, session: DbSession
) -> CustomerOut:
    out = CustomerOut.model_validate(
        await catalog.update_customer(session, ctx, customer_id, patch)
    )
    await commit(session)
    return out


@router.get("/items")
async def list_items(
    ctx: CurrentBusiness,
    session: DbSession,
    q: str | None = None,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ItemOut]:
    rows = await catalog.list_items(
        session, ctx, q=q, include_archived=include_archived, limit=limit, offset=offset
    )
    return [ItemOut.model_validate(i) for i in rows]


@router.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(ctx: CurrentBusiness, data: ItemIn, session: DbSession) -> ItemOut:
    out = ItemOut.model_validate(await catalog.create_item(session, ctx, data))
    await commit(session)
    return out


@router.get("/items/{item_id}")
async def get_item(ctx: CurrentBusiness, item_id: uuid.UUID, session: DbSession) -> ItemOut:
    return ItemOut.model_validate(await catalog.get_item(session, ctx, item_id))


@router.patch("/items/{item_id}")
async def update_item(
    ctx: CurrentBusiness, item_id: uuid.UUID, patch: ItemPatch, session: DbSession
) -> ItemOut:
    out = ItemOut.model_validate(await catalog.update_item(session, ctx, item_id, patch))
    await commit(session)
    return out
