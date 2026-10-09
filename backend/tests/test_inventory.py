from typing import Any

from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import CUSTOMER, draft, issue, setup
from tests.test_notifications import Jobs, dispatch, inbox, team


async def item(owner: Browser, bid: str, **fields: Any) -> dict[str, Any]:
    body = {"name": "ספל", "item_type": "product", "unit_price": "40", **fields}
    response = await owner.post(f"/api/v1/businesses/{bid}/items", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def adjust(owner: Browser, bid: str, item_id: str, **body: Any) -> Any:
    return await owner.post(
        f"/api/v1/businesses/{bid}/inventory/{item_id}/adjustments",
        json={"reason": "ספירה", **body},
    )


async def stock(owner: Browser, bid: str) -> dict[str, Any]:
    response = await owner.get(f"/api/v1/businesses/{bid}/inventory")
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def level(data: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(r for r in data["items"] if r["item"]["id"] == item_id)


async def sell(owner: Browser, bid: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    invoice = await draft(owner, bid, lines=lines)
    issued = await issue(owner, bid, invoice["id"])
    assert issued.status_code == 200, issued.text
    result: dict[str, Any] = issued.json()
    return result


def line(item_id: str, quantity: str, price: str = "40") -> dict[str, Any]:
    return {"item_id": item_id, "description": "x", "quantity": quantity, "unit_price": price}


async def test_average_cost_sales_and_returns(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        assert (await adjust(owner, bid, mug["id"], change="10", unit_cost="20")).status_code == 201
        await adjust(owner, bid, mug["id"], change="10", unit_cost="30")
        assert level(await stock(owner, bid), mug["id"])["average_cost"] == "25.0000"

        invoice = await sell(owner, bid, [line(mug["id"], "3")])
        after_sale = level(await stock(owner, bid), mug["id"])
        assert after_sale["quantity"] == "17.000"
        assert after_sale["value"] == "425.00"

        base = f"/api/v1/businesses/{bid}/documents"
        credit = (await owner.post(f"{base}/{invoice['id']}/credit-note")).json()
        assert credit["returns_stock"] is True
        await issue(owner, bid, credit["id"])
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "20.000"

        # A price-only credit leaves stock alone.
        price_only = (await owner.post(f"{base}/{invoice['id']}/credit-note")).json()
        await owner.patch(
            f"{base}/{price_only['id']}",
            json={"returns_stock": False, "lines": [line(mug["id"], "1", "10")]},
        )
        await issue(owner, bid, price_only["id"])
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "20.000"

        history = (
            await owner.get(f"/api/v1/businesses/{bid}/inventory/{mug['id']}/movements")
        ).json()
        assert [(m["kind"], m["quantity"], m["balance_after"]) for m in history] == [
            ("return", "3.000", "20.000"),
            ("sale", "-3.000", "17.000"),
            ("adjustment", "10.000", "20.000"),
            ("adjustment", "10.000", "10.000"),
        ]
        assert history[1]["unit_cost"] == "25.0000"  # goods leave at the average cost
        assert history[1]["document_id"] == invoice["id"]


async def test_kits_take_their_components_out(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        box = await item(owner, bid, name="קופסה", track_inventory=True)
        wrap = await item(owner, bid, name="אריזה", item_type="service")
        await adjust(owner, bid, mug["id"], change="9", unit_cost="20")
        await adjust(owner, bid, box["id"], change="5", unit_cost="3")
        kit = await item(
            owner,
            bid,
            name="סט מתנה",
            item_type="kit",
            unit_price="150",
            track_inventory=True,  # ignored: a kit's stock is its components'
            components=[
                {"item_id": mug["id"], "quantity": "2"},
                {"item_id": box["id"], "quantity": "1"},
                {"item_id": wrap["id"], "quantity": "1"},
            ],
        )
        assert kit["track_inventory"] is False
        assert [c["quantity"] for c in kit["components"]] == ["2.000", "1.000", "1.000"]
        [listed] = (await stock(owner, bid))["kits"]
        assert listed["available"] == "4"  # 9 mugs / 2 per kit

        await sell(owner, bid, [line(kit["id"], "2", "150"), line(mug["id"], "1")])

        data = await stock(owner, bid)
        assert level(data, mug["id"])["quantity"] == "4.000"  # 9 - 2*2 - 1
        assert level(data, box["id"])["quantity"] == "3.000"
        assert data["kits"][0]["available"] == "2"
        moves = (
            await owner.get(f"/api/v1/businesses/{bid}/inventory/{mug['id']}/movements")
        ).json()
        assert sorted((m["quantity"], m["kit_item_id"]) for m in moves[:2]) == [
            ("-1.000", None),
            ("-4.000", kit["id"]),
        ]


async def test_selling_below_zero_is_allowed(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        await adjust(owner, bid, mug["id"], change="1", unit_cost="20")
        await sell(owner, bid, [line(mug["id"], "3")])
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "-2.000"
        assert level(await stock(owner, bid), mug["id"])["value"] == "0.00"


async def test_count_sets_the_quantity(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        await adjust(owner, bid, mug["id"], change="10", unit_cost="20")
        counted = await adjust(owner, bid, mug["id"], counted="7", reason="ספירת סוף שנה")
        assert counted.json()["quantity"] == "-3.000"
        assert counted.json()["reason"] == "ספירת סוף שנה"
        same = await adjust(owner, bid, mug["id"], counted="7")
        assert same.json()["error"]["code"] == "adjustment_no_change"
        both = await adjust(owner, bid, mug["id"], counted="7", change="1")
        assert both.json()["error"]["code"] == "adjustment_needs_quantity"
        service = await item(owner, bid, name="ייעוץ", item_type="service")
        untracked = await adjust(owner, bid, service["id"], change="1")
        assert untracked.json()["error"]["code"] == "stock_not_tracked"


async def test_low_stock_alerts_managers_once(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with team(idp, sent_jobs) as (_, owner, bid, member, accountant):
        mug = await item(owner, bid, track_inventory=True, min_stock="5")
        await adjust(owner, bid, mug["id"], change="6", unit_cost="20")
        await sell(member, bid, [line(mug["id"], "2")])  # 6 -> 4: below the minimum
        await sell(member, bid, [line(mug["id"], "1")])  # still below: no second alert
        await dispatch()

        alerts = [n for n in await inbox(owner, bid) if n["event"] == "low_stock"]
        assert len(alerts) == 1
        assert alerts[0]["title"] == "מלאי נמוך"
        assert alerts[0]["body"] == "ספל: נותרו 4 (מינימום 5)"
        assert alerts[0]["link"] == "/inventory"
        assert [n for n in await inbox(accountant, bid) if n["event"] == "low_stock"] == []
        assert data_is_low(await stock(owner, bid), mug["id"])


def data_is_low(data: dict[str, Any], item_id: str) -> bool:
    return bool(level(data, item_id)["low"])


async def test_kit_rules(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        base = f"/api/v1/businesses/{bid}/items"
        empty = await owner.post(base, json={"name": "סט", "item_type": "kit"})
        assert empty.json()["error"]["code"] == "kit_needs_components"
        kit = await item(
            owner,
            bid,
            name="סט",
            item_type="kit",
            components=[{"item_id": mug["id"], "quantity": "1"}],
        )
        nested = await owner.post(
            base,
            json={
                "name": "סט גדול",
                "item_type": "kit",
                "components": [{"item_id": kit["id"], "quantity": "1"}],
            },
        )
        assert nested.json()["error"]["code"] == "kit_in_kit"
        not_kit = await owner.post(
            base, json={"name": "x", "components": [{"item_id": mug["id"], "quantity": "1"}]}
        )
        assert not_kit.json()["error"]["code"] == "components_need_kit"
        becomes_kit = await owner.patch(f"{base}/{mug['id']}", json={"item_type": "kit"})
        assert becomes_kit.json()["error"]["code"] == "kit_in_kit"  # it is inside a kit

        renamed = await owner.patch(
            f"{base}/{kit['id']}", json={"components": [{"item_id": mug["id"], "quantity": "3"}]}
        )
        assert renamed.json()["components"] == [{"item_id": mug["id"], "quantity": "3.000"}]
        cleared = await owner.patch(f"{base}/{mug['id']}", json={"min_stock": "2"})
        assert cleared.json()["min_stock"] == "2.000"
        cleared = await owner.patch(f"{base}/{mug['id']}", json={"min_stock": None})
        assert cleared.json()["min_stock"] is None


async def test_viewers_cannot_adjust(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with team(idp, sent_jobs) as (_, owner, bid, member, accountant):
        mug = await item(owner, bid, track_inventory=True)
        assert (await adjust(accountant, bid, mug["id"], change="1")).status_code == 403
        assert (await stock(accountant, bid))["items"][0]["item"]["id"] == mug["id"]
        assert (await adjust(member, bid, mug["id"], change="1")).status_code == 201
        assert CUSTOMER  # the shared test customer is used by the invoices above
