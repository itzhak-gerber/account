import os

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.ops.migrate import prepare

ADMIN = os.environ.get(
    "APP_TEST_ADMIN_DATABASE_URL", "postgresql+asyncpg://invoice:invoice@localhost:5432/invoice"
)


async def test_prepare_is_repeatable_and_gives_keycloak_its_own_database() -> None:
    admin = make_url(ADMIN)
    # The app role keeps the password the test suite connects with.
    await prepare(admin, "invoice_app", "kc-test-password")
    await prepare(admin, "invoice_app", "kc-test-password")

    keycloak = create_async_engine(
        admin.set(username="keycloak", password="kc-test-password", database="keycloak")
    )
    async with keycloak.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS kc_probe (id int)"))
        await conn.execute(text("DROP TABLE kc_probe"))
        # Keycloak's login cannot even connect to the app's database.
        allowed = await conn.scalar(
            text("SELECT has_database_privilege('keycloak', 'invoice', 'CONNECT')")
        )
    await keycloak.dispose()
    assert allowed is False

    app = create_async_engine(admin.set(username="invoice_app", password="invoice_app"))
    async with app.connect() as conn:
        assert await conn.scalar(text("SELECT current_user")) == "invoice_app"
    await app.dispose()


async def test_prepare_creates_a_missing_database_owned_by_the_admin() -> None:
    admin = make_url(ADMIN)
    fresh = admin.set(database="invoice_prepare_probe")
    maintenance = create_async_engine(admin.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with maintenance.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS invoice_prepare_probe"))

    await prepare(fresh, "invoice_app", None)

    async with maintenance.connect() as conn:
        owner = await conn.scalar(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname = 'invoice_prepare_probe'"
            )
        )
        await conn.execute(text("DROP DATABASE invoice_prepare_probe"))
    await maintenance.dispose()
    assert owner == admin.username
