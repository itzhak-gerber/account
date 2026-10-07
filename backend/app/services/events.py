"""Domain events (transactional outbox). Written in the same transaction as the change they
describe; the worker turns them into notifications (see services/notifications.py)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import after_commit
from app.jobs import queue
from app.models import OutboxEvent

DISPATCH_JOB = "dispatch_outbox"


async def _kick() -> None:
    # One dispatch job at a time; a periodic run picks up anything this one misses.
    await queue.enqueue(DISPATCH_JOB, _job_id=DISPATCH_JOB)


def emit(
    session: AsyncSession, business_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> None:
    session.add(OutboxEvent(business_id=business_id, event_type=event_type, payload=payload))
    after_commit(session, _kick)
