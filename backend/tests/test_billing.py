"""Plans: trial for new businesses, modules, read-only after the plan ends, quotas."""

import json
import os
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.billing import today
from tests.fake_idp import FakeIdP
from tests.helpers import app_client
from tests.test_documents import draft, issue, setup
from tests.test_expense_capture import photo, scan
from tests.test_inventory import adjust, item
from tests.test_purchasing import receive, supplier


async def _sql(query: str, **params: Any) -> list[Any]:
    engine = create_async_engine(os.environ["APP_TEST_ADMIN_DATABASE_URL"])
    async with engine.begin() as conn:
        result = await conn.execute(text(query), params)
        rows = list(result.all()) if result.returns_rows else []
    await engine.dispose()
    return rows


async def set_terms(bid: str, **terms: Any) -> None:
    """Change what the business's current plan allows."""
    await _sql(
        "UPDATE subscriptions SET terms = terms || CAST(:terms AS jsonb) WHERE business_id = :b",
        terms=json.dumps(terms),
        b=bid,
    )


async def end_plan(bid: str) -> None:
    await _sql(
        "UPDATE subscriptions SET starts_on = :start, ends_on = :end WHERE business_id = :b",
        start=today() - timedelta(days=40),
        end=today(),
        b=bid,
    )


async def usage(bid: str, kind: str) -> list[str | None]:
    rows = await _sql(
        "SELECT overage_price FROM usage_events WHERE business_id = :b AND kind = :k "
        "ORDER BY created_at",
        b=bid,
        k=kind,
    )
    return [None if r[0] is None else f"{r[0]:.2f}" for r in rows]


async def test_a_new_business_starts_with_the_trial(idp: FakeIdP) -> None:
    async with app_client() as client:
        _, bid = await setup(client, idp)
        [row] = await _sql(
            "SELECT kind, starts_on, ends_on, terms FROM subscriptions WHERE business_id = :b",
            b=bid,
        )
        assert row.kind == "trial"
        assert (row.starts_on, row.ends_on) == (today(), today() + timedelta(days=30))
        assert row.terms["modules"] == ["inventory", "scanning"]


async def test_after_the_plan_ends_the_business_is_read_only(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        issued = await issue(owner, bid, (await draft(owner, bid))["id"])
        assert issued.status_code == 200, issued.text
        await end_plan(bid)

        base = f"/api/v1/businesses/{bid}"
        refused = await owner.post(f"{base}/customers", json={"name": "לקוח"})
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "subscription_expired"
        refused = await owner.post(f"{base}/documents", json={"type": "tax_invoice", "lines": []})
        assert refused.json()["error"]["code"] == "subscription_expired"

        # Everything stays visible, and the owner can still manage access and export.
        assert (await owner.get(f"{base}/documents")).status_code == 200
        assert (await owner.get(f"{base}/documents/{issued.json()['id']}/pdf")).status_code == 200
        invited = await owner.post(
            f"{base}/invitations", json={"email": "cpa@example.com", "role": "accountant"}
        )
        assert invited.status_code == 201, invited.text
        exported = await owner.post(f"{base}/exports", json={})
        assert exported.status_code in (201, 202), exported.text


async def test_modules_not_in_the_plan_are_refused(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        cup = await item(owner, bid, track_inventory=True)
        await set_terms(bid, modules=[])
        base = f"/api/v1/businesses/{bid}"

        refused = await adjust(owner, bid, cup["id"], change="5")
        assert refused.status_code == 403
        assert refused.json()["error"] == {
            "code": "module_not_included",
            "message": "The 'inventory' module is not part of this business's plan",
            "details": {"module": "inventory"},
        }
        tracked = await owner.post(
            f"{base}/items",
            json={
                "name": "קומקום",
                "item_type": "product",
                "unit_price": "90",
                "track_inventory": True,
            },
        )
        assert tracked.json()["error"]["code"] == "module_not_included"
        kit = await owner.post(
            f"{base}/items",
            json={
                "name": "סט",
                "item_type": "kit",
                "unit_price": "100",
                "components": [{"item_id": cup["id"], "quantity": "2"}],
            },
        )
        assert kit.json()["error"]["code"] == "module_not_included"
        north = await supplier(owner, bid)
        received = await receive(
            owner,
            bid,
            north["id"],
            lines=[{"item_id": cup["id"], "quantity": "3", "unit_cost": "10"}],
        )
        assert received.json()["error"]["code"] == "module_not_included"
        scanned = await scan(owner, bid, photo())
        assert scanned.json()["error"]["code"] == "module_not_included"

        # The base stays open: plain items, purchase orders, documents, viewing stock.
        assert (await item(owner, bid, name="שירות", item_type="service"))["id"]
        renamed = await owner.patch(f"{base}/items/{cup['id']}", json={"name": "ספל גדול"})
        assert renamed.status_code == 200, renamed.text
        assert (await owner.get(f"{base}/inventory")).status_code == 200
        assert (await issue(owner, bid, (await draft(owner, bid))["id"])).status_code == 200


async def test_documents_past_the_quota_are_issued_and_charged(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await set_terms(bid, documents_per_month=1, document_overage_price="2.50")

        quote = await draft(owner, bid, type="quote")
        assert (await issue(owner, bid, quote["id"])).status_code == 200  # not counted
        for _ in range(2):
            assert (await issue(owner, bid, (await draft(owner, bid))["id"])).status_code == 200

        assert await usage(bid, "document") == [None, "2.50"]


async def test_scans_stop_at_the_quota_unless_the_plan_charges_for_more(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await set_terms(bid, scans_per_month=1, scan_overage_price=None)

        assert (await scan(owner, bid, photo())).status_code == 201
        refused = await scan(owner, bid, photo())
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "scan_quota_exceeded"

        await set_terms(bid, scan_overage_price="1.00")
        assert (await scan(owner, bid, photo())).status_code == 201
        assert await usage(bid, "scan") == [None, "1.00"]
