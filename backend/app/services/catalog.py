"""Customers and items of a business."""

import uuid
from typing import Any

from sqlalchemy import Select, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.errors import AppError, NotFound
from app.models import Customer, Item, ItemComponent, ItemType
from app.schemas.catalog import ComponentIn, CustomerIn, CustomerPatch, ItemIn, ItemPatch
from app.services import audit
from app.services.permissions import Permission, require


def _search[T: (Customer, Item)](
    query: Select[T], text: str | None, fields: list[Any]
) -> Select[T]:
    if text:
        pattern = f"%{text.strip().replace('%', '').replace('_', '')}%"
        query = query.where(or_(*[f.ilike(pattern) for f in fields]))
    return query


async def _apply_patch(obj: Any, patch: Any) -> dict[str, dict[str, str]]:
    changes: dict[str, dict[str, str]] = {}
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is None and field != "email":
            continue
        value = "" if value is None else value
        if getattr(obj, field) != value:
            changes[field] = {"from": str(getattr(obj, field)), "to": str(value)}
            setattr(obj, field, value)
    return changes


# --- customers -------------------------------------------------------------------------


async def list_customers(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    q: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Customer]:
    require(ctx.role, Permission.VIEW_CATALOG)
    query = select(Customer).where(Customer.business_id == ctx.business_id)
    if not include_archived:
        query = query.where(Customer.is_archived.is_(False))
    query = _search(query, q, [Customer.name, Customer.tax_id, Customer.email, Customer.phone])
    return list(await session.scalars(query.order_by(Customer.name).limit(limit).offset(offset)))


async def get_customer(
    session: AsyncSession, ctx: BusinessContext, customer_id: uuid.UUID
) -> Customer:
    require(ctx.role, Permission.VIEW_CATALOG)
    customer = await session.get(Customer, customer_id)
    if customer is None or customer.business_id != ctx.business_id:
        raise NotFound("Customer not found", code="customer_not_found")
    return customer


async def create_customer(
    session: AsyncSession, ctx: BusinessContext, data: CustomerIn
) -> Customer:
    require(ctx.role, Permission.MANAGE_CATALOG)
    values = data.model_dump()
    values["email"] = values["email"] or ""
    customer = Customer(business_id=ctx.business_id, is_archived=False, **values)
    session.add(customer)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="customer.created",
        entity_type="customer",
        entity_id=customer.id,
        business_id=ctx.business_id,
        changes={"name": customer.name},
    )
    return customer


async def update_customer(
    session: AsyncSession, ctx: BusinessContext, customer_id: uuid.UUID, patch: CustomerPatch
) -> Customer:
    require(ctx.role, Permission.MANAGE_CATALOG)
    customer = await get_customer(session, ctx, customer_id)
    changes = await _apply_patch(customer, patch)
    if changes:
        await session.flush()
        await session.refresh(customer)
        await audit.record(
            session,
            ctx.principal,
            action="customer.updated",
            entity_type="customer",
            entity_id=customer.id,
            business_id=ctx.business_id,
            changes=changes,
        )
    return customer


# --- items -----------------------------------------------------------------------------


async def list_items(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    q: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Item]:
    require(ctx.role, Permission.VIEW_CATALOG)
    query = select(Item).where(Item.business_id == ctx.business_id)
    if not include_archived:
        query = query.where(Item.is_archived.is_(False))
    query = _search(query, q, [Item.name, Item.sku, Item.barcode, Item.description])
    return list(await session.scalars(query.order_by(Item.name).limit(limit).offset(offset)))


async def get_item(session: AsyncSession, ctx: BusinessContext, item_id: uuid.UUID) -> Item:
    require(ctx.role, Permission.VIEW_CATALOG)
    item = await session.get(Item, item_id)
    if item is None or item.business_id != ctx.business_id:
        raise NotFound("Item not found", code="item_not_found")
    return item


class InvalidItem(AppError):
    code = "invalid_item"


async def _set_components(
    session: AsyncSession, ctx: BusinessContext, item: Item, components: list[ComponentIn]
) -> None:
    """Kits are made of plain products and services (one level: no kit inside a kit)."""
    if item.item_type != ItemType.KIT:
        if components:
            raise InvalidItem("Only kits have components", code="components_need_kit")
        if inspect(item).transient or item.components:
            item.components = []
        return
    if not components:
        raise InvalidItem("A kit needs at least one component", code="kit_needs_components")
    ids = [c.item_id for c in components]
    if len(set(ids)) != len(ids):
        raise InvalidItem("Each item can appear once in a kit", code="kit_duplicate_component")
    found = {
        i.id: i
        for i in await session.scalars(
            select(Item).where(Item.business_id == ctx.business_id, Item.id.in_(ids))
        )
    }
    for component in components:
        part = found.get(component.item_id)
        if part is None or part.id == item.id:
            raise NotFound("Component not found", code="item_not_found")
        if part.item_type == ItemType.KIT:
            raise InvalidItem("A kit cannot contain another kit", code="kit_in_kit")
    item.components = [
        ItemComponent(
            business_id=ctx.business_id,
            component_item_id=c.item_id,
            position=n,
            quantity=c.quantity,
        )
        for n, c in enumerate(components)
    ]


def _normalise_stock_fields(item: Item) -> None:
    # Only products keep stock; a kit's stock is that of its components.
    if item.item_type != ItemType.PRODUCT:
        item.track_inventory = False
        item.min_stock = None


async def create_item(session: AsyncSession, ctx: BusinessContext, data: ItemIn) -> Item:
    require(ctx.role, Permission.MANAGE_CATALOG)
    item = Item(
        business_id=ctx.business_id,
        is_archived=False,
        **data.model_dump(exclude={"components"}),
    )
    _normalise_stock_fields(item)
    # Before the item joins the session, so setting the collection loads nothing.
    await _set_components(session, ctx, item, data.components)
    session.add(item)
    await session.flush()
    if item.components:
        await session.refresh(item, ["components"])
    await audit.record(
        session,
        ctx.principal,
        action="item.created",
        entity_type="item",
        entity_id=item.id,
        business_id=ctx.business_id,
        changes={"name": item.name},
    )
    return item


async def update_item(
    session: AsyncSession, ctx: BusinessContext, item_id: uuid.UUID, patch: ItemPatch
) -> Item:
    require(ctx.role, Permission.MANAGE_CATALOG)
    item = await get_item(session, ctx, item_id)
    was_kit = item.item_type == ItemType.KIT
    changes = await _apply_patch(item, patch.model_copy(update={"components": None}))
    if "min_stock" in patch.model_fields_set and patch.min_stock is None and item.min_stock:
        changes["min_stock"] = {"from": str(item.min_stock), "to": ""}
        item.min_stock = None
    if item.item_type == ItemType.KIT and not was_kit:
        used = await session.scalar(
            select(ItemComponent.kit_item_id).where(ItemComponent.component_item_id == item.id)
        )
        if used:
            raise InvalidItem("This item is part of a kit", code="kit_in_kit")
    _normalise_stock_fields(item)
    if patch.components is not None or item.item_type != ItemType.KIT:
        if patch.components is not None or item.components:
            await _set_components(session, ctx, item, patch.components or [])
            if patch.components is not None:
                changes["components"] = {"from": "", "to": str(len(patch.components))}
    if changes:
        await session.flush()
        await session.refresh(item)
        await audit.record(
            session,
            ctx.principal,
            action="item.updated",
            entity_type="item",
            entity_id=item.id,
            business_id=ctx.business_id,
            changes=changes,
        )
    return item
