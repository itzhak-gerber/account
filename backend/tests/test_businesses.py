import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import VALID_BUSINESS, Browser, app_client, browser_login


async def create_business(browser: Browser, **overrides: object) -> dict[str, object]:
    response = await browser.post("/api/v1/businesses", json={**VALID_BUSINESS, **overrides})
    assert response.status_code == 201, response.text
    business: dict[str, object] = response.json()["business"]
    return business


async def test_creating_a_business_requires_two_factor(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"), mfa=False)

        response = await browser.post("/api/v1/businesses", json=VALID_BUSINESS)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "mfa_required"


async def test_create_business_makes_creator_owner(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"), mfa=True)

        business = await create_business(browser)

        assert business["display_name"] == "דוגמה בע״מ"
        me = (await browser.get("/api/v1/me")).json()
        assert [(m["business"]["id"], m["role"]) for m in me["memberships"]] == [
            (business["id"], "owner")
        ]


@pytest.mark.parametrize("tax_id", ["123456789", "12", "abcdefghi"])
async def test_invalid_tax_id_rejected(idp: FakeIdP, tax_id: str) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"), mfa=True)

        response = await browser.post(
            "/api/v1/businesses", json={**VALID_BUSINESS, "tax_id": tax_id}
        )

        assert response.status_code == 422


async def test_owner_updates_business_and_it_is_audited(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"), mfa=True)
        business = await create_business(browser)
        base = f"/api/v1/businesses/{business['id']}"

        updated = await browser.patch(base, json={"display_name": "דוגמה", "phone": "03-1234567"})
        log = (await browser.get(f"{base}/audit-log")).json()

        assert updated.status_code == 200
        assert updated.json()["display_name"] == "דוגמה"
        assert [e["action"] for e in log] == ["business.updated", "business.created"]
        assert log[0]["changes"]["display_name"] == {"from": "דוגמה בע״מ", "to": "דוגמה"}
        assert log[0]["actor_email"] == "a@example.com"
        assert log[0]["actor_channel"] == "web"


async def test_other_users_cannot_see_a_business(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner = await browser_login(client, idp, FakeUser(email="owner@example.com"), mfa=True)
        business = await create_business(owner)
        stranger = await browser_login(client, idp, FakeUser(email="other@example.com"), mfa=True)

        for path in ("", "/members", "/audit-log", "/invitations"):
            response = await stranger.get(f"/api/v1/businesses/{business['id']}{path}")
            assert response.status_code == 404, path
            assert response.json()["error"]["code"] == "business_not_found"
        assert (
            await stranger.patch(f"/api/v1/businesses/{business['id']}", json={})
        ).status_code == 404
        assert (await stranger.get("/api/v1/me")).json()["memberships"] == []


async def test_database_enforces_isolation_even_without_app_filters(idp: FakeIdP) -> None:
    """Row-level security: raw SQL as the app role only sees rows the context allows."""
    async with app_client() as client:
        owner = await browser_login(client, idp, FakeUser(email="owner@example.com"), mfa=True)
        business = await create_business(owner)
        stranger = await browser_login(client, idp, FakeUser(email="other@example.com"), mfa=True)
        stranger_id = (await stranger.get("/api/v1/me")).json()["user"]["id"]

    engine = create_async_engine(os.environ["APP_DATABASE_URL"])
    async with engine.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM businesses"))).scalar() == 0
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": stranger_id})
        assert (await conn.execute(text("SELECT count(*) FROM businesses"))).scalar() == 0
        assert (await conn.execute(text("SELECT count(*) FROM business_members"))).scalar() == 0
        assert (
            await conn.execute(text("SELECT count(*) FROM audit_logs"))
        ).scalar() == 1  # own login
        with pytest.raises(Exception, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO business_members (id, business_id, user_id, role)"
                    " VALUES (:id, :b, :u, 'owner')"
                ),
                {"id": str(uuid.uuid4()), "b": business["id"], "u": stranger_id},
            )
    await engine.dispose()


async def test_audit_log_is_append_only(idp: FakeIdP) -> None:
    async with app_client() as client:
        await browser_login(client, idp, FakeUser(email="a@example.com"))

    engine = create_async_engine(os.environ["APP_TEST_ADMIN_DATABASE_URL"])
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            await conn.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            await conn.execute(text("DELETE FROM audit_logs"))
    await engine.dispose()
