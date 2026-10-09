from typing import Any

from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import setup
from tests.test_inventory import item, level, stock
from tests.test_notifications import Jobs, team


async def supplier(owner: Browser, bid: str, name: str = "סיטונאות הצפון") -> dict[str, Any]:
    response = await owner.post(
        f"/api/v1/businesses/{bid}/suppliers", json={"name": name, "phone": "04-1234567"}
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def order(owner: Browser, bid: str, supplier_id: str, lines: list[dict[str, Any]]) -> Any:
    return await owner.post(
        f"/api/v1/businesses/{bid}/purchase-orders",
        json={"supplier_id": supplier_id, "order_date": "2026-10-01", "lines": lines},
    )


async def receive(owner: Browser, bid: str, supplier_id: str, **body: Any) -> Any:
    return await owner.post(
        f"/api/v1/businesses/{bid}/goods-receipts",
        json={"supplier_id": supplier_id, "receipt_date": "2026-10-05", **body},
    )


async def test_order_receive_in_parts_and_average_cost(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        mug = await item(owner, bid, track_inventory=True)
        await owner.post(
            f"/api/v1/businesses/{bid}/inventory/{mug['id']}/adjustments",
            json={"change": "10", "unit_cost": "20", "reason": "מלאי פתיחה"},
        )

        created = await order(
            owner,
            bid,
            north["id"],
            [
                {"item_id": mug["id"], "description": "ספל", "quantity": "30", "unit_cost": "30"},
                {"description": "הובלה", "quantity": "1", "unit_cost": "100"},
            ],
        )
        assert created.status_code == 201, created.text
        po = created.json()
        assert (po["number"], po["status"], po["total"]) == (1, "open", "1000.00")
        mug_line = po["lines"][0]["id"]

        first = await receive(
            owner,
            bid,
            north["id"],
            purchase_order_id=po["id"],
            supplier_reference="ת.מ. 5521",
            lines=[
                {
                    "item_id": mug["id"],
                    "order_line_id": mug_line,
                    "quantity": "10",
                    "unit_cost": "30",
                }
            ],
        )
        assert first.status_code == 201, first.text
        assert first.json()["number"] == 1
        # 10 at 20 plus 10 at 30: the average is 25.
        after = level(await stock(owner, bid), mug["id"])
        assert (after["quantity"], after["average_cost"]) == ("20.000", "25.0000")

        base = f"/api/v1/businesses/{bid}/purchase-orders/{po['id']}"
        partial = (await owner.get(base)).json()
        assert partial["status"] == "partial"
        assert partial["lines"][0]["received_quantity"] == "10.000"
        # Nothing can be changed on an order once goods arrived.
        locked = await owner.patch(base, json={"notes": "x"})
        assert locked.json()["error"]["code"] == "purchase_order_locked"

        await receive(
            owner,
            bid,
            north["id"],
            purchase_order_id=po["id"],
            lines=[
                {
                    "item_id": mug["id"],
                    "order_line_id": mug_line,
                    "quantity": "20",
                    "unit_cost": "30",
                }
            ],
        )
        # Every product arrived (the freight line is not goods): the order is complete.
        assert (await owner.get(base)).json()["status"] == "received"
        cancelled = await owner.post(f"{base}/cancel")
        assert cancelled.json()["error"]["code"] == "purchase_order_closed"
        closed = await receive(
            owner,
            bid,
            north["id"],
            purchase_order_id=po["id"],
            lines=[{"item_id": mug["id"], "quantity": "1", "unit_cost": "30"}],
        )
        assert closed.json()["error"]["code"] == "purchase_order_closed"

        history = (
            await owner.get(f"/api/v1/businesses/{bid}/inventory/{mug['id']}/movements")
        ).json()
        assert history[0]["kind"] == "receipt"
        assert history[0]["goods_receipt_id"] is not None
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "40.000"


async def test_order_received_in_full_and_edits_before(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        mug = await item(owner, bid, track_inventory=True)
        po = (
            await order(
                owner,
                bid,
                north["id"],
                [{"item_id": mug["id"], "description": "ספל", "quantity": "5", "unit_cost": "8"}],
            )
        ).json()
        base = f"/api/v1/businesses/{bid}/purchase-orders/{po['id']}"
        edited = await owner.patch(
            base,
            json={
                "lines": [
                    {"item_id": mug["id"], "description": "ספל", "quantity": "6", "unit_cost": "8"}
                ]
            },
        )
        assert edited.json()["total"] == "48.00"
        line_id = edited.json()["lines"][0]["id"]
        await receive(
            owner,
            bid,
            north["id"],
            purchase_order_id=po["id"],
            lines=[
                {"item_id": mug["id"], "order_line_id": line_id, "quantity": "6", "unit_cost": "8"}
            ],
        )
        assert (await owner.get(base)).json()["status"] == "received"
        assert (await owner.post(f"{base}/cancel")).json()["error"][
            "code"
        ] == "purchase_order_closed"


async def test_receipt_rules(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        south = await supplier(owner, bid, "ספקי הדרום")
        mug = await item(owner, bid, track_inventory=True)
        plate = await item(owner, bid, name="צלחת", track_inventory=True)
        service = await item(owner, bid, name="ייעוץ", item_type="service")
        po = (
            await order(
                owner,
                bid,
                north["id"],
                [{"item_id": mug["id"], "description": "ספל", "quantity": "5", "unit_cost": "8"}],
            )
        ).json()
        line_id = po["lines"][0]["id"]

        async def code(supplier_id: str, **body: Any) -> str:
            result: str = (await receive(owner, bid, supplier_id, **body)).json()["error"]["code"]
            return result

        assert (
            await code(
                south["id"],
                purchase_order_id=po["id"],
                lines=[{"item_id": mug["id"], "quantity": "1", "unit_cost": "8"}],
            )
            == "receipt_supplier"
        )
        assert (
            await code(
                north["id"],
                purchase_order_id=po["id"],
                lines=[
                    {
                        "item_id": plate["id"],
                        "order_line_id": line_id,
                        "quantity": "1",
                        "unit_cost": "8",
                    }
                ],
            )
            == "receipt_order_line_mismatch"
        )
        assert (
            await code(
                north["id"], lines=[{"item_id": service["id"], "quantity": "1", "unit_cost": "8"}]
            )
            == "receipt_not_product"
        )
        # Nothing moved after the refusals.
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "0"

        # A receipt without an order is fine too.
        direct = await receive(
            owner,
            bid,
            south["id"],
            lines=[{"item_id": plate["id"], "quantity": "4", "unit_cost": "12.5"}],
        )
        assert direct.status_code == 201, direct.text
        assert direct.json()["total"] == "50.00"
        assert level(await stock(owner, bid), plate["id"])["average_cost"] == "12.5000"


async def test_supplier_invoices(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        base = f"/api/v1/businesses/{bid}/supplier-invoices"
        body = {
            "supplier_id": north["id"],
            "invoice_number": "A-1001",
            "invoice_date": "2026-10-05",
            "due_date": "2026-11-05",
            "net_amount": "1000.00",
            "vat_amount": "180.00",
        }
        created = await owner.post(base, json=body)
        assert created.status_code == 201, created.text
        invoice = created.json()
        assert (invoice["total"], invoice["paid_date"]) == ("1180.00", None)

        twice = await owner.post(base, json=body)
        assert twice.status_code == 409
        assert twice.json()["error"]["code"] == "supplier_invoice_duplicate"

        paid = await owner.patch(f"{base}/{invoice['id']}", json={"paid_date": "2026-10-20"})
        assert paid.json()["paid_date"] == "2026-10-20"
        assert (await owner.get(base, params={"unpaid": "true"})).json() == []
        unpaid = await owner.patch(f"{base}/{invoice['id']}", json={"paid_date": None})
        assert unpaid.json()["paid_date"] is None
        assert len((await owner.get(base, params={"unpaid": "true"})).json()) == 1

        assert (await owner.delete(f"{base}/{invoice['id']}")).status_code == 204
        assert (await owner.get(base)).json() == []


async def test_purchasing_permissions(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with team(idp, sent_jobs) as (_, _owner, bid, member, accountant):
        north = await supplier(member, bid)
        # The accountant sees purchasing but cannot change it.
        assert (await accountant.get(f"/api/v1/businesses/{bid}/suppliers")).json()[0]["id"] == (
            north["id"]
        )
        refused = await accountant.post(f"/api/v1/businesses/{bid}/suppliers", json={"name": "ספק"})
        assert refused.status_code == 403
