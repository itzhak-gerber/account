"""Test setup: real PostgreSQL (as the restricted app role, so RLS applies), real Redis,
and a fake OpenID Connect provider that signs real JWTs."""

import os
import tempfile

os.environ.setdefault("APP_ENVIRONMENT", "test")
os.environ.setdefault(
    "APP_DATABASE_URL", "postgresql+asyncpg://invoice_app:invoice_app@localhost:5432/invoice"
)
os.environ.setdefault(
    "APP_TEST_ADMIN_DATABASE_URL", "postgresql+asyncpg://invoice:invoice@localhost:5432/invoice"
)
os.environ.setdefault("APP_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("APP_PUBLIC_URL", "http://localhost")
os.environ.setdefault("APP_OIDC_ISSUER", "http://idp.test/realms/invoice")
os.environ.setdefault("APP_MCP_ALLOWED_HOSTS", '["localhost", "localhost:*"]')
os.environ.setdefault("APP_STORAGE_DIR", tempfile.mkdtemp(prefix="invoice-test-files-"))

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import oidc
from app.core import db, redis, storage
from app.core.config import get_settings
from app.jobs import queue
from tests.fake_idp import FakeIdP

TABLES = [
    "notifications",
    "notification_preferences",
    "user_devices",
    "outbox_events",
    "document_relations",
    "document_payments",
    "document_lines",
    "documents",
    "files",
    "document_sequences",
    "items",
    "customers",
    "audit_logs",
    "invitations",
    "business_members",
    "businesses",
    "users",
]


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    # Fresh engines/clients per test: each test runs on its own event loop.
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    redis.get_redis.cache_clear()
    storage.get_storage.cache_clear()
    admin = create_async_engine(os.environ["APP_TEST_ADMIN_DATABASE_URL"])
    async with admin.begin() as conn:
        # Session-local switch so the append-only trigger does not block cleanup.
        await conn.execute(text("SET session_replication_role = replica"))
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    await admin.dispose()
    await redis.get_redis().flushdb()
    yield
    await redis.get_redis().aclose()
    await db.get_engine().dispose()


@pytest.fixture
def idp() -> FakeIdP:
    fake = FakeIdP(get_settings())
    oidc.set_oidc_client(fake.client())
    return fake


@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Background jobs are recorded, never sent to Redis (every test gets this)."""
    jobs: list[tuple[str, dict[str, Any]]] = []

    async def fake_enqueue(function: str, **kwargs: Any) -> None:
        jobs.append((function, kwargs))

    monkeypatch.setattr(queue, "enqueue", fake_enqueue)
    return jobs
