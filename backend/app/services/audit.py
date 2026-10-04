"""Audit trail writer. Every state-changing service call records who did what, and from where."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.models import AuditLog
from app.services.permissions import Permission, require


async def record(
    session: AsyncSession,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    changes: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            business_id=business_id,
            actor_user_id=principal.user_id,
            actor_channel=principal.channel,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes or {},
            ip=principal.ip,
            user_agent=principal.user_agent,
        )
    )
    await session.flush()


async def list_entries(
    session: AsyncSession, ctx: BusinessContext, *, limit: int = 50, before: uuid.UUID | None = None
) -> list[AuditLog]:
    require(ctx.role, Permission.VIEW_AUDIT_LOG)
    query = select(AuditLog).where(AuditLog.business_id == ctx.business_id)
    if before is not None:
        cursor = await session.get(AuditLog, before)
        if cursor is not None:
            query = query.where(AuditLog.created_at < cursor.created_at)
    query = query.order_by(AuditLog.created_at.desc()).limit(min(limit, 200))
    return list(await session.scalars(query))
