from typing import Any

from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import draft, issue, setup
from tests.test_inventory import item, level, line, stock


async def deliver(owner: Browser, bid: str, lines: list[dict[str, Any]], **fields: Any) -> Any:
    note = await draft(owner, bid, type="delivery_note", lines=lines, **fields)
    issued = await issue(owner, bid, note["id"])
    assert issued.status_code == 200, issued.text
    return issued.json()


async def opening(owner: Browser, bid: str, item_id: str, quantity: str) -> None:
    await owner.post(
        f"/api/v1/businesses/{bid}/inventory/{item_id}/adjustments",
        json={"change": quantity, "unit_cost": "10", "reason": "מלאי פתיחה"},
    )


async def test_invoice_from_a_delivery_note_does_not_take_stock_twice(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        await opening(owner, bid, mug["id"], "10")

        note = await deliver(owner, bid, [line(mug["id"], "4")])
        assert (note["type"], note["number"], note["delivery_status"]) == (
            "delivery_note",
            1,
            "open",
        )
        assert note["payment_status"] is None  # not a demand for payment
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "6.000"

        base = f"/api/v1/businesses/{bid}/documents"
        invoice = (
            await owner.post(f"{base}/{note['id']}/convert", json={"type": "tax_invoice"})
        ).json()
        # The customer is billed for 5: 4 were delivered already, one more leaves now.
        await owner.patch(f"{base}/{invoice['id']}", json={"lines": [line(mug["id"], "5")]})
        assert (await issue(owner, bid, invoice["id"])).status_code == 200
        assert level(await stock(owner, bid), mug["id"])["quantity"] == "5.000"

        billed = (await owner.get(f"{base}/{note['id']}")).json()
        assert billed["delivery_status"] == "invoiced"
        again = await owner.post(f"{base}/{note['id']}/convert", json={"type": "tax_invoice"})
        assert again.json()["error"]["code"] == "delivery_note_invoiced"

        pdf = await owner.get(f"{base}/{invoice['id']}/pdf", params={"variant": "copy"})
        assert pdf.status_code == 200


async def test_consolidated_invoice_bills_several_notes(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        mug = await item(owner, bid, track_inventory=True)
        await opening(owner, bid, mug["id"], "20")
        first = await deliver(owner, bid, [line(mug["id"], "2")], issue_date="2026-10-01")
        second = await deliver(owner, bid, [line(mug["id"], "3")], issue_date="2026-10-02")
        other = await deliver(owner, bid, [line(mug["id"], "1")], customer={"name": "לקוח אחר"})
        base = f"/api/v1/businesses/{bid}/documents"

        open_notes = (await owner.get(base, params={"uninvoiced": "true"})).json()
        assert {d["id"] for d in open_notes} == {first["id"], second["id"], other["id"]}

        mixed = await owner.post(
            f"{base}/invoice-delivery-notes",
            json={"delivery_note_ids": [first["id"], other["id"]]},
        )
        assert mixed.json()["error"]["code"] == "delivery_notes_customers"

        created = await owner.post(
            f"{base}/invoice-delivery-notes",
            json={"delivery_note_ids": [second["id"], first["id"]]},
        )
        assert created.status_code == 201, created.text
        invoice = created.json()
        assert invoice["type"] == "tax_invoice"
        assert [ln["quantity"] for ln in invoice["lines"]] == ["2.000", "3.000"]  # by note date
        assert invoice["subtotal"] == "200.00"
        assert {r["id"] for r in invoice["related"]} == {first["id"], second["id"]}

        # A second draft for the same note can exist, but only one invoice can be issued.
        rival = (
            await owner.post(f"{base}/{first['id']}/convert", json={"type": "tax_invoice"})
        ).json()
        assert (await issue(owner, bid, invoice["id"])).status_code == 200
        refused = await issue(owner, bid, rival["id"])
        assert refused.json()["error"]["code"] == "delivery_note_invoiced"

        assert level(await stock(owner, bid), mug["id"])["quantity"] == "14.000"
        open_notes = (await owner.get(base, params={"uninvoiced": "true"})).json()
        assert [d["id"] for d in open_notes] == [other["id"]]


async def test_exempt_dealers_deliver_but_cannot_invoice_with_vat(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp, business_type="exempt_dealer")
        types = (await owner.get(f"/api/v1/businesses/{bid}/document-types")).json()
        assert "delivery_note" in {t["type"] for t in types}
        note = await deliver(
            owner, bid, [{"description": "ארגז", "quantity": "1", "unit_price": "0"}]
        )
        refused = await owner.post(
            f"/api/v1/businesses/{bid}/documents/invoice-delivery-notes",
            json={"delivery_note_ids": [note["id"]]},
        )
        assert refused.json()["error"]["code"] == "document_type_not_allowed"
