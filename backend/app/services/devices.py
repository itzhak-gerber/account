"""Recognise the browsers a user signs in from, and alert them when a new one appears.

Each browser gets a long-lived random cookie; only its hash is stored. The first device an
account ever uses is recorded silently; every later unknown one triggers a "new device"
notification (in the app, and by email unless the user turned that off).
"""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import after_commit
from app.core.errors import NotFound
from app.emails.templates import notification_email
from app.jobs import queue
from app.models import Notification, NotificationEvent, User, UserDevice
from app.schemas.notifications import DeviceOut
from app.services import notifications

DEVICE_COOKIE = "invoice_device"
DEVICE_COOKIE_DAYS = 400  # the longest browsers keep a cookie

_BROWSERS = (
    ("Edge", r"Edg(e|A|iOS)?/"),
    ("Samsung Internet", r"SamsungBrowser/"),
    ("Firefox", r"(Firefox|FxiOS)/"),
    ("Chrome", r"(Chrome|CriOS)/"),
    ("Safari", r"Safari/"),
)
_SYSTEMS = (
    ("iPhone", r"iPhone"),
    ("iPad", r"iPad"),
    ("Android", r"Android"),
    ("Windows", r"Windows"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("Linux", r"Linux"),
)


def describe(user_agent: str) -> str:
    """A short human label such as "Chrome · Windows" (never relied on for security)."""
    browser = next((name for name, rx in _BROWSERS if re.search(rx, user_agent)), "דפדפן")
    system = next((name for name, rx in _SYSTEMS if re.search(rx, user_agent)), "")
    return f"{browser} · {system}" if system else browser


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def recognise(
    session: AsyncSession, user: User, token: str | None, user_agent: str, ip: str
) -> str:
    """Record this sign-in's device and alert on a new one. Runs in the user's own security
    context. Returns the device cookie value to (re)set."""
    token = token if token and len(token) >= 32 else secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    device = await session.scalar(
        select(UserDevice).where(
            UserDevice.user_id == user.id, UserDevice.device_hash == _hash(token)
        )
    )
    if device is not None:
        device.last_seen_at, device.last_ip = now, ip[:64]
        return token
    known = await session.scalar(
        select(func.count()).select_from(UserDevice).where(UserDevice.user_id == user.id)
    )
    device = UserDevice(
        user_id=user.id,
        device_hash=_hash(token),
        label=describe(user_agent)[:100],
        last_ip=ip[:64],
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(device)
    await session.flush()
    if known:
        await _alert(session, user, device, now)
    return token


async def _alert(session: AsyncSession, user: User, device: UserDevice, when: datetime) -> None:
    event = NotificationEvent.NEW_DEVICE_LOGIN
    prefs = (await notifications.preferences_for(session, [user.id], event))[user.id]
    local = when.astimezone(ZoneInfo(get_settings().timezone)).strftime("%d/%m/%Y %H:%M")
    title = "כניסה לחשבון ממכשיר חדש"
    body = (
        f"{device.label}, {local}"
        + (f", כתובת IP {device.last_ip}" if device.last_ip else "")
        + ". אם זה לא את/ה, יש לשנות סיסמה ולהתנתק מכל המכשירים."
    )
    if prefs["in_app"]:
        session.add(
            Notification(
                user_id=user.id,
                business_id=None,
                event=event.value,
                title=title,
                body=body,
                link="/profile",
                dedupe_key=f"device:{device.id}",
            )
        )
    if prefs["email"]:
        email = notification_email(
            to=user.email,
            business_name=None,
            title=title,
            link=f"{get_settings().public_url.rstrip('/')}/profile",
            intro="נרשמה כניסה לחשבון שלך ממכשיר או מדפדפן שלא השתמשת בו קודם.",
            details=(
                ("מכשיר", device.label),
                ("מועד", local),
                *((("כתובת IP", device.last_ip),) if device.last_ip else ()),
                ("אם זה לא את/ה", "שנו סיסמה ובחרו 'התנתקות מכל המכשירים' בפרופיל"),
            ),
        )

        async def send() -> None:
            await queue.enqueue(
                "send_email", to=email.to, subject=email.subject, html=email.html, text=email.text
            )

        after_commit(session, send)


async def list_devices(
    session: AsyncSession, user_id: uuid.UUID, token: str | None
) -> list[DeviceOut]:
    current = _hash(token) if token else None
    rows = await session.scalars(
        select(UserDevice)
        .where(UserDevice.user_id == user_id)
        .order_by(UserDevice.last_seen_at.desc())
    )
    return [
        DeviceOut.model_validate(d).model_copy(update={"current": d.device_hash == current})
        for d in rows
    ]


async def forget(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
    """Forget a device; signing in from it again counts as a new device."""
    device = await session.get(UserDevice, device_id)
    if device is None or device.user_id != user_id:
        raise NotFound("Device not found", code="device_not_found")
    await session.delete(device)
