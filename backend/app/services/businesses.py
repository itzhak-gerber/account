"""Businesses (tenants) and their members."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.core.config import get_settings
from app.core.db import set_rls_context
from app.core.errors import Conflict, Forbidden, MfaRequired, NotFound
from app.models import Business, BusinessMember, Role, User
from app.schemas.identity import BusinessIn, BusinessPatch, MemberOut
from app.services import audit
from app.services.permissions import Permission, has_permission, require


async def create_business(
    session: AsyncSession, principal: Principal, data: BusinessIn
) -> Business:
    # The creator becomes the owner, and owners must use two-factor authentication.
    if get_settings().require_mfa_for_admins and not principal.mfa:
        raise MfaRequired("Two-factor authentication is required to create a business")
    business_id = uuid.uuid4()
    await set_rls_context(session, business_id=business_id)
    values = data.model_dump()
    values["display_name"] = values["display_name"] or values["legal_name"]
    values["email"] = values["email"] or ""
    business = Business(id=business_id, **values)
    session.add(business)
    await session.flush()
    member = BusinessMember(business_id=business_id, user_id=principal.user_id, role=Role.OWNER)
    session.add(member)
    await session.flush()
    await audit.record(
        session,
        principal,
        action="business.created",
        entity_type="business",
        entity_id=business_id,
        business_id=business_id,
        changes={"after": data.model_dump(mode="json")},
    )
    return business


async def list_for_user(session: AsyncSession, principal: Principal) -> list[tuple[Business, Role]]:
    rows = await session.execute(
        select(Business, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == principal.user_id)
        .order_by(Business.display_name)
    )
    return [(business, Role(role)) for business, role in rows.all()]


async def get_business(session: AsyncSession, ctx: BusinessContext) -> Business:
    require(ctx.role, Permission.VIEW_BUSINESS)
    business = await session.get(Business, ctx.business_id)
    if business is None:
        raise NotFound("Business not found", code="business_not_found")
    return business


async def update_business(
    session: AsyncSession, ctx: BusinessContext, patch: BusinessPatch
) -> Business:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    business = await get_business(session, ctx)
    changes: dict[str, dict[str, object]] = {}
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is None and field != "email":
            continue
        value = value if value is not None else ""
        old = getattr(business, field)
        if old != value:
            changes[field] = {"from": str(old), "to": str(value)}
            setattr(business, field, value)
    if changes:
        await session.flush()
        await audit.record(
            session,
            ctx.principal,
            action="business.updated",
            entity_type="business",
            entity_id=business.id,
            business_id=business.id,
            changes=changes,
        )
    return business


async def list_members(session: AsyncSession, ctx: BusinessContext) -> list[MemberOut]:
    require(ctx.role, Permission.VIEW_MEMBERS)
    rows = await session.execute(
        select(BusinessMember, User)
        .join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == ctx.business_id)
        .order_by(BusinessMember.created_at)
    )
    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=Role(m.role),
            joined_at=m.created_at,
        )
        for m, u in rows.all()
    ]


async def _get_member(
    session: AsyncSession, ctx: BusinessContext, member_id: uuid.UUID
) -> BusinessMember:
    member = await session.get(BusinessMember, member_id)
    if member is None or member.business_id != ctx.business_id:
        raise NotFound("Member not found", code="member_not_found")
    return member


async def _owner_count(session: AsyncSession, business_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(BusinessMember)
        .where(BusinessMember.business_id == business_id, BusinessMember.role == Role.OWNER)
    )
    return int(count or 0)


async def change_member_role(
    session: AsyncSession, ctx: BusinessContext, member_id: uuid.UUID, new_role: Role
) -> BusinessMember:
    require(ctx.role, Permission.MANAGE_MEMBERS)
    member = await _get_member(session, ctx, member_id)
    old_role = Role(member.role)
    if old_role == new_role:
        return member
    if Role.OWNER in (old_role, new_role):
        require(ctx.role, Permission.MANAGE_OWNERS)
    if old_role == Role.OWNER and await _owner_count(session, ctx.business_id) <= 1:
        raise Conflict("A business must keep at least one owner", code="last_owner")
    member.role = new_role
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="member.role_changed",
        entity_type="business_member",
        entity_id=member.id,
        business_id=ctx.business_id,
        changes={"user_id": str(member.user_id), "from": old_role, "to": new_role},
    )
    return member


async def remove_member(session: AsyncSession, ctx: BusinessContext, member_id: uuid.UUID) -> None:
    member = await _get_member(session, ctx, member_id)
    leaving_self = member.user_id == ctx.principal.user_id
    if not leaving_self:
        require(ctx.role, Permission.MANAGE_MEMBERS)
        if member.role == Role.OWNER and not has_permission(ctx.role, Permission.MANAGE_OWNERS):
            raise Forbidden("Only owners can remove owners", code="permission_denied")
    if member.role == Role.OWNER and await _owner_count(session, ctx.business_id) <= 1:
        raise Conflict("A business must keep at least one owner", code="last_owner")
    await session.delete(member)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="member.left" if leaving_self else "member.removed",
        entity_type="business_member",
        entity_id=member.id,
        business_id=ctx.business_id,
        changes={"user_id": str(member.user_id), "role": member.role},
    )
