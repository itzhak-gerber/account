"""Prepare the database and apply migrations. Run before each rollout (in Azure as a job):

    python -m app.ops.migrate

Connects as the server admin (APP_DATABASE_URL + APP_DATABASE_PASSWORD) and makes sure that
- the restricted role the app connects as exists, with the password from APP_DB_ROLE_PASSWORD
  (row-level security applies to it; it owns nothing);
- Keycloak has its own role and database (KEYCLOAK_DB_PASSWORD), separate from app data;
then runs `alembic upgrade head`. Safe to run any number of times.
"""

import asyncio
import os
import re
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

log = structlog.get_logger()
APP_ROLE = "invoice_app"
KEYCLOAK = "keycloak"


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ident(value: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise ValueError(f"unexpected identifier: {value}")
    return value


async def _ensure_role(conn: AsyncConnection, role: str, password: str) -> None:
    exists = await conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
    verb = "ALTER" if exists else "CREATE"
    await conn.execute(text(f"{verb} ROLE {_ident(role)} LOGIN PASSWORD {_literal(password)}"))


async def _ensure_database(conn: AsyncConnection, name: str) -> None:
    # Created by the admin, so the admin owns it and may create tables in it (PostgreSQL 15+
    # no longer lets every role create in "public").
    if not await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": name}):
        await conn.execute(text(f"CREATE DATABASE {_ident(name)}"))


async def prepare(admin_url: URL, app_password: str, keycloak_password: str | None) -> None:
    database = _ident(admin_url.database or "")
    # Roles and databases are managed from the maintenance database "postgres".
    engine = create_async_engine(admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await _ensure_database(conn, database)
            await _ensure_role(conn, APP_ROLE, app_password)
            # Only the app role (and the admin) may connect to the app's database.
            await conn.execute(text(f"REVOKE CONNECT ON DATABASE {database} FROM PUBLIC"))
            await conn.execute(text(f"GRANT CONNECT ON DATABASE {database} TO {APP_ROLE}"))
            if keycloak_password:
                await _ensure_role(conn, KEYCLOAK, keycloak_password)
                await _ensure_database(conn, KEYCLOAK)
                await conn.execute(text(f"GRANT ALL ON DATABASE {KEYCLOAK} TO {KEYCLOAK}"))
    finally:
        await engine.dispose()
    if keycloak_password:
        kc_engine = create_async_engine(admin_url.set(database=KEYCLOAK))
        try:
            async with kc_engine.begin() as conn:
                await conn.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {KEYCLOAK}"))
        finally:
            await kc_engine.dispose()
    log.info("migrate.prepared", database=database, keycloak=bool(keycloak_password))


def upgrade() -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    log.info("migrate.upgraded")


def main() -> None:
    settings = get_settings()
    asyncio.run(
        prepare(
            make_url(settings.database_url),
            os.environ["APP_DB_ROLE_PASSWORD"],
            os.environ.get("KEYCLOAK_DB_PASSWORD"),
        )
    )
    upgrade()


if __name__ == "__main__":
    main()
