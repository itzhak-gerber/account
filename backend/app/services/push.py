"""Web Push: notifications on phones (installed app) and desktop browsers.

The browser gives us an endpoint on its push service plus encryption keys; we encrypt a small
payload and POST it there, signed with our VAPID key. Only the title and an app link are sent:
lock screens are public, so amounts and customer names stay in the app.
"""

import base64
import json
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import anyio
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.core.config import get_settings
from app.core.db import after_commit
from app.core.errors import AppError
from app.jobs import queue
from app.models import PushSubscription

log = structlog.get_logger()

# Push services of the browsers we support. The endpoint comes from the browser, so anything
# else is refused: otherwise a user could make our worker call arbitrary URLs.
PUSH_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Edge (Android), Samsung Internet
    "updates.push.services.mozilla.com",  # Firefox
    ".push.apple.com",  # Safari, iPhone and iPad home-screen apps
    ".notify.windows.com",  # Edge on Windows
)


def endpoint_allowed(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == allowed or (allowed.startswith(".") and host.endswith(allowed))
        for allowed in PUSH_HOSTS
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@lru_cache
def _private_key(encoded: str) -> ec.EllipticCurvePrivateKey:
    der = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    key = serialization.load_der_private_key(der, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("VAPID key must be an EC P-256 key")
    return key


def public_key() -> str | None:
    """The VAPID public key browsers subscribe with (uncompressed point, base64url)."""
    encoded = get_settings().vapid_private_key
    if not encoded:
        return None
    point = (
        _private_key(encoded)
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return _b64url(point)


def enabled() -> bool:
    return bool(get_settings().vapid_private_key)


async def subscribe(
    session: AsyncSession,
    principal: Principal,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    label: str,
) -> None:
    if not endpoint_allowed(endpoint):
        raise AppError("Unsupported push service", code="push_endpoint_not_allowed")
    await session.execute(
        insert(PushSubscription)
        .values(
            id=uuid.uuid4(),
            user_id=principal.user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            label=label[:100],
        )
        .on_conflict_do_update(
            constraint="uq_push_subscriptions_device",
            set_={"p256dh": p256dh, "auth": auth, "label": label[:100]},
        )
    )


async def unsubscribe(session: AsyncSession, principal: Principal, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == principal.user_id, PushSubscription.endpoint == endpoint
        )
    )


async def count(session: AsyncSession, principal: Principal) -> int:
    rows = await session.scalars(
        select(PushSubscription.id).where(PushSubscription.user_id == principal.user_id)
    )
    return len(rows.all())


def queue_push(
    session: AsyncSession, user_ids: list[uuid.UUID], *, title: str, link: str, tag: str
) -> None:
    """Push to every device of these users once the transaction commits."""
    if not user_ids or not enabled():
        return

    async def send() -> None:
        await queue.enqueue(
            "send_push", user_ids=[str(u) for u in user_ids], title=title, link=link, tag=tag
        )

    after_commit(session, send)


def payload(*, title: str, link: str, tag: str) -> str:
    return json.dumps({"title": title, "link": link or "/", "tag": tag[:100]}, ensure_ascii=False)


def send_one(subscription: dict[str, Any], data: str) -> int:
    """Encrypt and deliver one message (blocking; run in a thread). Returns the HTTP status."""
    from pywebpush import WebPushException, webpush  # imported lazily: heavy and worker-only

    settings = get_settings()
    subject = settings.vapid_subject or settings.public_url
    if not subject.startswith(("mailto:", "https://")):
        subject = "mailto:noreply@invoice.local"
    try:
        response = webpush(
            subscription_info=subscription,
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": subject},
            ttl=24 * 3600,
            timeout=10,
        )
        return int(getattr(response, "status_code", 201))
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else 0
        log.warning(
            "push.failed",
            service=urlsplit(subscription["endpoint"]).hostname,
            status=status,
            error=str(exc)[:200],
        )
        return int(status)


@dataclass
class Outcome:
    devices: int = 0
    sent: int = 0
    # Devices the push service reported as unsubscribed or expired (404/410): to forget.
    gone: list[uuid.UUID] | None = None
    # Other refusals: the push service's HTTP status (0 = it could not be reached).
    failures: list[int] | None = None


async def send_to(targets: list[Any], data: str) -> Outcome:
    """Deliver ``data`` to rows with id, endpoint, p256dh and auth."""
    outcome = Outcome(devices=len(targets), gone=[], failures=[])
    for target in targets:
        if not endpoint_allowed(target.endpoint):
            continue
        subscription = {
            "endpoint": target.endpoint,
            "keys": {"p256dh": target.p256dh, "auth": target.auth},
        }
        status = await anyio.to_thread.run_sync(send_one, subscription, data)
        if status in (404, 410):
            assert outcome.gone is not None
            outcome.gone.append(target.id)
        elif 200 <= status < 300:
            outcome.sent += 1
        else:
            assert outcome.failures is not None
            outcome.failures.append(status)
    return outcome


async def test(session: AsyncSession, principal: Principal) -> Outcome:
    """Send a test notification to this user's devices now, and report what happened."""
    targets = list(
        await session.scalars(
            select(PushSubscription).where(PushSubscription.user_id == principal.user_id)
        )
    )
    if not enabled():
        return Outcome(devices=len(targets), gone=[], failures=[])
    outcome = await send_to(
        targets, payload(title="התראת בדיקה מחשבוניות", link="/profile", tag="test")
    )
    if outcome.gone:
        await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(outcome.gone)))
    return outcome
