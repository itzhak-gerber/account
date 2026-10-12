"""The operator's plans, prices with linkage, selling plans, billing, and the business's view."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest

from app.core.config import get_settings
from app.services.billing import today
from app.services.plans import add_months
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import Browser, app_client, browser_login, second_client
from tests.test_billing import _sql
from tests.test_documents import draft, issue, setup
from tests.test_notifications import Jobs, notification_emails

OPERATOR = "ops@example.com"


@pytest.fixture(autouse=True)
async def _billing_tables() -> AsyncIterator[None]:
    """Plans and settings are shared by all businesses: put them back after each test."""
    yield
    await _sql("DELETE FROM usage_events")
    await _sql("DELETE FROM subscriptions")
    await _sql(
        "UPDATE billing_settings SET trial_days = 30, new_business_discount_percent = 0, "
        "new_business_discount_periods = 0, "
        "trial_plan_id = (SELECT id FROM plans WHERE name = 'ניסיון')"
    )
    await _sql("DELETE FROM plans WHERE name <> 'ניסיון'")
    await _sql("DELETE FROM index_values")


@pytest.fixture
def operators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "operator_emails", [OPERATOR])


async def operator(client: Any, idp: FakeIdP, *, mfa: bool = True) -> Browser:
    return await browser_login(client, idp, FakeUser(email=OPERATOR), mfa=mfa)


PLAN = {
    "name": "עסקי",
    "description": "מסמכים ומלאי",
    "modules": ["inventory"],
    "duration_months": 12,
    "price": "1200.00",
    "documents_per_month": 1,
    "document_overage_price": "3.00",
    "scans_per_month": 0,
}


async def create_plan(ops: Browser, **fields: Any) -> dict[str, Any]:
    created = await ops.post("/api/v1/admin/plans", json={**PLAN, **fields})
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


async def test_only_operators_with_two_factor_reach_the_admin_screens(
    idp: FakeIdP, operators: None
) -> None:
    async with app_client() as client:
        owner, _ = await setup(client, idp)
        refused = await owner.get("/api/v1/admin/plans")
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "operator_only")
        assert (await owner.get("/api/v1/me")).json()["is_operator"] is False

        async with second_client(client) as other:
            ops = await operator(other, idp, mfa=False)
            refused = await ops.get("/api/v1/admin/plans")
            assert refused.json()["error"]["code"] == "mfa_required"
            ops = await operator(other, idp)
            assert (await ops.get("/api/v1/admin/plans")).status_code == 200
            assert (await ops.get("/api/v1/me")).json()["is_operator"] is True


async def test_linked_prices_follow_the_index(idp: FakeIdP, operators: None) -> None:
    async with app_client() as client:
        ops = await operator(client, idp)
        missing = await ops.post("/api/v1/admin/plans", json={**PLAN, "linkage": "cpi"})
        assert missing.json()["error"]["code"] == "index_missing"

        cpi = await ops.post(
            "/api/v1/admin/index-values",
            json={"kind": "cpi", "period": "2026-08-15", "value": "100"},
        )
        assert cpi.json()["period"] == "2026-08-01"  # CPI is by month
        plan = await create_plan(ops, linkage="cpi")
        assert (plan["base_index"], plan["current_price"]) == ("100.0000", "1200.00")

        await ops.post(
            "/api/v1/admin/index-values",
            json={"kind": "cpi", "period": "2026-09-01", "value": "102.5"},
        )
        plans = {p["name"]: p for p in (await ops.get("/api/v1/admin/plans")).json()}
        assert plans["עסקי"]["current_price"] == "1230.00"


async def test_selling_a_plan_fixes_its_terms_and_price(
    idp: FakeIdP, operators: None, sent_jobs: Jobs
) -> None:
    async with app_client() as client, second_client(client) as other:
        owner, bid = await setup(client, idp)
        ops = await operator(other, idp)
        plan = await create_plan(ops)
        saved = await ops.put(
            "/api/v1/admin/settings",
            json={
                "trial_plan_id": None,
                "trial_days": 0,
                "new_business_discount_percent": "50",
                "new_business_discount_periods": 1,
            },
        )
        assert saved.status_code == 200, saved.text

        base = f"/api/v1/admin/businesses/{bid}/subscriptions"
        first = await ops.post(base, json={"plan_id": plan["id"], "notes": "שנה ראשונה"})
        assert first.status_code == 201, first.text
        bought = first.json()
        start = today()
        assert (bought["kind"], bought["starts_on"], bought["ends_on"]) == (
            "paid",
            start.isoformat(),
            add_months(start, 12).isoformat(),
        )
        assert (bought["price"], bought["discount_percent"]) == ("600.00", "50.00")
        assert bought["terms"]["documents_per_month"] == 1

        # Later changes to the plan do not touch what was bought.
        await ops.put(f"/api/v1/admin/plans/{plan['id']}", json={**PLAN, "price": "2000"})
        renewal = (await ops.post(base, json={"plan_id": plan["id"]})).json()
        assert renewal["starts_on"] == bought["ends_on"]  # follows the paid year
        assert (renewal["price"], renewal["discount_percent"]) == ("2000.00", "0.00")
        history = (await ops.get(base)).json()
        assert [h["price"] for h in history] == ["2000.00", "600.00", "0.00"]  # + the trial

        # The business sees its plan; documents past the quota are charged.
        for _ in range(2):
            assert (await issue(owner, bid, (await draft(owner, bid))["id"])).status_code == 200
        status = (await owner.get(f"/api/v1/businesses/{bid}/plan")).json()
        assert (status["name"], status["modules"], status["read_only"]) == (
            "עסקי",
            ["inventory"],
            False,
        )
        assert status["documents"] == {"used": 2, "quota": 1, "over": 1, "over_amount": "3.00"}
        assert [p["name"] for p in status["available_plans"]] == ["עסקי"]
        me = (await owner.get("/api/v1/me")).json()
        assert me["memberships"][0]["plan"]["modules"] == ["inventory"]

        report = (await ops.get("/api/v1/admin/billing")).json()
        [row] = report["rows"]
        assert (row["plan_charges"], row["documents_over"], row["documents_over_amount"]) == (
            "600.00",
            1,
            "3.00",
        )
        assert row["total"] == report["total"] == "603.00"
        xlsx = await ops.get("/api/v1/admin/billing", params={"format": "xlsx"})
        assert xlsx.content.startswith(b"PK")

        # Ending early: from that day the business is read-only.
        ended = await ops.post(
            f"{base}/{bought['id']}/end", json={"ends_on": (start + timedelta(days=1)).isoformat()}
        )
        assert ended.json()["ends_on"] == (start + timedelta(days=1)).isoformat()
        businesses = (await ops.get("/api/v1/admin/businesses")).json()
        assert [(b["tax_id"], b["documents_this_month"]) for b in businesses] == [("516179157", 2)]


async def test_quota_alerts_and_upgrade_requests(
    idp: FakeIdP, operators: None, sent_jobs: Jobs
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await _sql(
            "UPDATE subscriptions SET terms = terms || '{\"documents_per_month\": 5}'::jsonb"
        )
        for _ in range(5):
            assert (await issue(owner, bid, (await draft(owner, bid))["id"])).status_code == 200
        alerts = await _sql(
            "SELECT payload FROM outbox_events WHERE event_type = 'plan.quota' ORDER BY created_at"
        )
        assert [(a[0]["used"], a[0]["level"]) for a in alerts] == [(4, 80), (5, 100)]

        asked = await owner.post(
            f"/api/v1/businesses/{bid}/plan/upgrade-request",
            json={"module": "scanning", "message": "נשמח לסריקת חשבוניות"},
        )
        assert asked.status_code == 202, asked.text
        [email] = [e for e in notification_emails(sent_jobs) if e["to"] == OPERATOR]
        assert "מודול סריקת חשבוניות" in email["text"]
        assert "516179157" in email["text"]


async def test_reminders_before_the_plan_ends(idp: FakeIdP) -> None:
    async with app_client() as client:
        _, bid = await setup(client, idp)
        [[ends]] = await _sql("SELECT ends_on FROM subscriptions WHERE business_id = :b", b=bid)
        for days in (14, 3, 0):
            [[count]] = await _sql("SELECT enqueue_plan_reminders(:d)", d=ends - timedelta(days))
            assert count == 1
        [[again]] = await _sql("SELECT enqueue_plan_reminders(:d)", d=ends)
        assert again == 0
        [[none]] = await _sql("SELECT enqueue_plan_reminders(:d)", d=ends - timedelta(5))
        assert none == 0
