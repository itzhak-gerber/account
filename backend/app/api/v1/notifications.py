import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.auth.principal import CurrentBusiness, CurrentPrincipal, DbSession
from app.core.db import commit
from app.schemas.notifications import (
    DeviceOut,
    MarkRead,
    NotificationOut,
    PreferenceOut,
    PreferencesIn,
    PushConfig,
    PushSubscriptionIn,
    PushSubscriptionRef,
    PushTestResult,
    UnreadCount,
)
from app.services import devices, notifications, push
from app.services.devices import describe as describe_device

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


@router.get("/me/devices")
async def list_devices(
    request: Request, principal: CurrentPrincipal, session: DbSession
) -> list[DeviceOut]:
    token = request.cookies.get(devices.DEVICE_COOKIE)
    return await devices.list_devices(session, principal.user_id, token)


@router.delete("/me/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_device(
    device_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await devices.forget(session, principal.user_id, device_id)
    await commit(session)


@router.get("/me/push")
async def push_config(principal: CurrentPrincipal, session: DbSession) -> PushConfig:
    """The key browsers subscribe with, and how many devices this user registered."""
    return PushConfig(public_key=push.public_key(), devices=await push.count(session, principal))


@router.put("/me/push", status_code=status.HTTP_204_NO_CONTENT)
async def push_subscribe(
    request: Request, principal: CurrentPrincipal, data: PushSubscriptionIn, session: DbSession
) -> None:
    await push.subscribe(
        session,
        principal,
        endpoint=data.endpoint,
        p256dh=data.keys.p256dh,
        auth=data.keys.auth,
        label=describe_device(request.headers.get("user-agent", "")),
    )
    await commit(session)


@router.post("/me/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def push_unsubscribe(
    principal: CurrentPrincipal, data: PushSubscriptionRef, session: DbSession
) -> None:
    await push.unsubscribe(session, principal, data.endpoint)
    await commit(session)


@router.post("/me/push/test")
async def push_test(principal: CurrentPrincipal, session: DbSession) -> PushTestResult:
    """Send a test notification to all of this user's devices now, and say what happened."""
    outcome = await push.test(session, principal)
    await commit(session)
    return PushTestResult(devices=outcome.devices, sent=outcome.sent, gone=len(outcome.gone or []))
