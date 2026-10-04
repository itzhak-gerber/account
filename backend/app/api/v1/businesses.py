import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.auth.principal import CurrentBusiness, CurrentPrincipal, DbSession
from app.core.db import commit
from app.models import User
from app.schemas.identity import (
    AuditEntryOut,
    BusinessIn,
    BusinessOut,
    BusinessPatch,
    InvitationAccept,
    InvitationIn,
    InvitationOut,
    InvitationPreview,
    MemberOut,
    MembershipOut,
    RoleChange,
)
from app.services import audit, businesses, invitations

router = APIRouter(tags=["businesses"])


@router.post("/businesses", status_code=status.HTTP_201_CREATED)
async def create_business(
    data: BusinessIn, principal: CurrentPrincipal, session: DbSession
) -> MembershipOut:
    business = await businesses.create_business(session, principal, data)
    out = MembershipOut(business=BusinessOut.model_validate(business), role="owner")
    await commit(session)
    return out


@router.get("/businesses/{business_id}")
async def get_business(ctx: CurrentBusiness, session: DbSession) -> BusinessOut:
    return BusinessOut.model_validate(await businesses.get_business(session, ctx))


@router.patch("/businesses/{business_id}")
async def update_business(
    ctx: CurrentBusiness, patch: BusinessPatch, session: DbSession
) -> BusinessOut:
    out = BusinessOut.model_validate(await businesses.update_business(session, ctx, patch))
    await commit(session)
    return out


@router.get("/businesses/{business_id}/members")
async def list_members(ctx: CurrentBusiness, session: DbSession) -> list[MemberOut]:
    return await businesses.list_members(session, ctx)


@router.patch("/businesses/{business_id}/members/{member_id}")
async def change_member_role(
    ctx: CurrentBusiness, member_id: uuid.UUID, change: RoleChange, session: DbSession
) -> list[MemberOut]:
    await businesses.change_member_role(session, ctx, member_id, change.role)
    out = await businesses.list_members(session, ctx)
    await commit(session)
    return out


@router.delete("/businesses/{business_id}/members/{member_id}", status_code=204)
async def remove_member(ctx: CurrentBusiness, member_id: uuid.UUID, session: DbSession) -> None:
    await businesses.remove_member(session, ctx, member_id)
    await commit(session)


@router.get("/businesses/{business_id}/invitations")
async def list_invitations(ctx: CurrentBusiness, session: DbSession) -> list[InvitationOut]:
    return [InvitationOut.model_validate(i) for i in await invitations.list_pending(session, ctx)]


@router.post("/businesses/{business_id}/invitations", status_code=201)
async def create_invitation(
    ctx: CurrentBusiness, data: InvitationIn, session: DbSession
) -> InvitationOut:
    invitation = await invitations.create_invitation(session, ctx, email=data.email, role=data.role)
    out = InvitationOut.model_validate(invitation)
    await commit(session)
    return out


@router.delete("/businesses/{business_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    ctx: CurrentBusiness, invitation_id: uuid.UUID, session: DbSession
) -> None:
    await invitations.revoke(session, ctx, invitation_id)
    await commit(session)


@router.get("/businesses/{business_id}/audit-log")
async def audit_log(
    ctx: CurrentBusiness,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: uuid.UUID | None = None,
) -> list[AuditEntryOut]:
    entries = await audit.list_entries(session, ctx, limit=limit, before=before)
    emails: dict[uuid.UUID, str] = {}
    for entry in entries:
        if entry.actor_user_id and entry.actor_user_id not in emails:
            user = await session.get(User, entry.actor_user_id)
            emails[entry.actor_user_id] = user.email if user else ""
    return [
        AuditEntryOut(
            id=e.id,
            actor_user_id=e.actor_user_id,
            actor_email=emails.get(e.actor_user_id) if e.actor_user_id else None,
            actor_channel=e.actor_channel,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            changes=e.changes,
            ip=str(e.ip) if e.ip else None,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/invitations/preview")
async def preview_invitation(
    principal: CurrentPrincipal, session: DbSession, token: Annotated[str, Query(min_length=20)]
) -> InvitationPreview:
    return await invitations.preview(session, token)


@router.post("/invitations/accept")
async def accept_invitation(
    data: InvitationAccept, principal: CurrentPrincipal, session: DbSession
) -> dict[str, uuid.UUID]:
    business_id = await invitations.accept(session, principal, data.token)
    await commit(session)
    return {"business_id": business_id}
