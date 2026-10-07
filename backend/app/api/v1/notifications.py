from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.principal import CurrentBusiness, CurrentPrincipal, DbSession
from app.core.db import commit
from app.schemas.notifications import (
    MarkRead,
    NotificationOut,
    PreferenceOut,
    PreferencesIn,
    UnreadCount,
)
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/businesses/{business_id}/notifications")
async def list_notifications(
    ctx: CurrentBusiness,
    session: DbSession,
    unread_only: bool = False,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[NotificationOut]:
    return await notifications.list_notifications(
        session, ctx, unread_only=unread_only, before=before, limit=limit
    )


@router.get("/businesses/{business_id}/notifications/unread-count")
async def unread_count(ctx: CurrentBusiness, session: DbSession) -> UnreadCount:
    return UnreadCount(unread=await notifications.unread_count(session, ctx))


@router.post("/businesses/{business_id}/notifications/read")
async def mark_read(ctx: CurrentBusiness, data: MarkRead, session: DbSession) -> UnreadCount:
    await notifications.mark_read(session, ctx, data.ids)
    await commit(session)
    return UnreadCount(unread=await notifications.unread_count(session, ctx))


@router.get("/me/notification-preferences")
async def get_preferences(principal: CurrentPrincipal, session: DbSession) -> list[PreferenceOut]:
    return await notifications.get_preferences(session, principal)


@router.put("/me/notification-preferences")
async def set_preferences(
    principal: CurrentPrincipal, data: PreferencesIn, session: DbSession
) -> list[PreferenceOut]:
    result = await notifications.set_preferences(session, principal, data.preferences)
    await commit(session)
    return result
