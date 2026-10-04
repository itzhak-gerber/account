"""Async SQLAlchemy engine, sessions, and the row-level-security context.

Each session carries the acting user and (inside a business) the active business in
``session.info``. At the start of every transaction they are applied with
``set_config(..., is_local => true)``, so they last exactly one transaction and can never
leak to another request through the connection pool.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import get_settings

_RLS_KEY = "rls_settings"


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def set_rls_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
    invitation_token_hash: str | None = None,
) -> None:
    """Set the security context; applies to the current transaction and every later one."""
    values = session.info.setdefault(_RLS_KEY, {})
    if user_id is not None:
        values["app.user_id"] = str(user_id)
    if business_id is not None:
        values["app.business_id"] = str(business_id)
    if invitation_token_hash is not None:
        values["app.invitation_token_hash"] = invitation_token_hash
    if session.in_transaction():
        for name, value in values.items():
            await session.execute(
                text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value}
            )


@event.listens_for(Session, "after_begin")
def _apply_rls_on_begin(session: Session, transaction: SessionTransaction, connection: Any) -> None:
    values = session.info.get(_RLS_KEY)
    if values:
        for name, value in values.items():
            connection.execute(
                text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value}
            )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Handlers commit explicitly."""
    async with get_sessionmaker()() as session:
        yield session


def after_commit(session: AsyncSession, callback: Callable[[], Awaitable[None]]) -> None:
    """Run ``callback`` only once the current work is committed (e.g. sending an email)."""
    session.info.setdefault("after_commit", []).append(callback)


async def commit(session: AsyncSession) -> None:
    await session.commit()
    callbacks = session.info.pop("after_commit", [])
    for callback in callbacks:
        await callback()
