"""Invite people to a business by email; they accept after signing in with that email."""

import hashlib
import secrets
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.core.config import get_settings
from app.core.db import after_commit, set_rls_context
from app.core.errors import Conflict, Forbidden, NotFound
from app.emails.templates import invitation_email
from app.jobs import queue
from app.models import Business, BusinessMember, Invitation, Role, User
from app.schemas.identity import InvitationPreview
from app.services import audit
from app.services.permissions import Permission, require


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _status(invitation: Invitation) -> str:
    if invitation.revoked_at:
        return "revoked"
    if invitation.accepted_at:
        return "accepted"
    if invitation.expires_at <= datetime.now(UTC):
        return "expired"
    return "pending"


async def create_invitation(
    session: AsyncSession, ctx: BusinessContext, *, email: str, role: Role
) -> Invitation:
    require(ctx.role, Permission.MANAGE_MEMBERS)
    if role == Role.OWNER:
        require(ctx.role, Permission.MANAGE_OWNERS)
    already_member = await session.scalar(
        select(BusinessMember.id)
        .join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == ctx.business_id, User.email == email)
    )
    if already_member:
        raise Conflict("This person is already a member", code="already_member")

    now = datetime.now(UTC)
    # A new invitation to the same address replaces any pending one.
    pending = await session.scalars(
        select(Invitation).where(
            Invitation.business_id == ctx.business_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    for old in pending:
        old.revoked_at = now

    business = await session.get(Business, ctx.business_id)
    inviter = await session.get(User, ctx.principal.user_id)
    assert business is not None and inviter is not None
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        business_id=ctx.business_id,
        email=email,
        role=role,
        business_name=business.display_name,
        invited_by_name=inviter.full_name or inviter.email,
        token_hash=hash_token(token),
        invited_by_user_id=inviter.id,
        expires_at=now + timedelta(days=settings.invitation_ttl_days),
    )
    session.add(invitation)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="invitation.created",
        entity_type="invitation",
        entity_id=invitation.id,
        business_id=ctx.business_id,
        changes={"email": email, "role": role},
    )

    message = invitation_email(
        to=email,
        business_name=invitation.business_name,
        invited_by=invitation.invited_by_name,
        role=role,
        link=f"{settings.public_url.rstrip('/')}/invite?token={token}",
        ttl_days=settings.invitation_ttl_days,
    )

    async def send() -> None:
        await queue.enqueue("send_email", **asdict(message))

    after_commit(session, send)
    return invitation


async def list_pending(session: AsyncSession, ctx: BusinessContext) -> list[Invitation]:
    require(ctx.role, Permission.MANAGE_MEMBERS)
    rows = await session.scalars(
        select(Invitation)
        .where(
            Invitation.business_id == ctx.business_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


async def revoke(session: AsyncSession, ctx: BusinessContext, invitation_id: uuid.UUID) -> None:
    require(ctx.role, Permission.MANAGE_MEMBERS)
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None or invitation.business_id != ctx.business_id:
        raise NotFound("Invitation not found", code="invitation_not_found")
    if invitation.role == Role.OWNER:
        require(ctx.role, Permission.MANAGE_OWNERS)
    if invitation.revoked_at is None and invitation.accepted_at is None:
        invitation.revoked_at = datetime.now(UTC)
        await session.flush()
        await audit.record(
            session,
            ctx.principal,
            action="invitation.revoked",
            entity_type="invitation",
            entity_id=invitation.id,
            business_id=ctx.business_id,
            changes={"email": invitation.email},
        )


async def _load_by_token(session: AsyncSession, token: str) -> Invitation:
    token_hash = hash_token(token)
    await set_rls_context(session, invitation_token_hash=token_hash)
    invitation = await session.scalar(select(Invitation).where(Invitation.token_hash == token_hash))
    if invitation is None:
        raise NotFound("Invitation not found", code="invitation_not_found")
    return invitation


async def preview(session: AsyncSession, token: str) -> InvitationPreview:
    invitation = await _load_by_token(session, token)
    return InvitationPreview(
        business_name=invitation.business_name,
        invited_by_name=invitation.invited_by_name,
        email=invitation.email,
        role=Role(invitation.role),
        expires_at=invitation.expires_at,
        status=_status(invitation),
    )


async def accept(session: AsyncSession, principal: Principal, token: str) -> uuid.UUID:
    invitation = await _load_by_token(session, token)
    status = _status(invitation)
    if status != "pending":
        raise Conflict(f"Invitation is {status}", code=f"invitation_{status}")
    if invitation.email.lower() != principal.email.lower():
        raise Forbidden(
            "This invitation was sent to a different email address",
            code="invitation_email_mismatch",
        )
    business_id = invitation.business_id
    await set_rls_context(session, business_id=business_id)
    exists = await session.scalar(
        select(BusinessMember.id).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == principal.user_id,
        )
    )
    if exists:
        raise Conflict("You are already a member of this business", code="already_member")
    member = BusinessMember(
        business_id=business_id, user_id=principal.user_id, role=invitation.role
    )
    session.add(member)
    invitation.accepted_at = datetime.now(UTC)
    invitation.accepted_by_user_id = principal.user_id
    await session.flush()
    await audit.record(
        session,
        principal,
        action="invitation.accepted",
        entity_type="business_member",
        entity_id=member.id,
        business_id=business_id,
        changes={"role": invitation.role, "invitation_id": str(invitation.id)},
    )
    return business_id
