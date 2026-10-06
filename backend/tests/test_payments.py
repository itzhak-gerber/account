import asyncio
from typing import Any

from app.services.documents import today
from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import CUSTOMER, draft, issue, setup


def receipt_body(amount: str, allocations: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    return {
        "type": "receipt",
        "customer": CUSTOMER,
        "lines": [],
        "payments": [
            {"method": "bank_transfer", "amount": amount, "payment_date": today().isoformat()}
        ],
        "allocations": allocations,
        **extra,
    }


async def issued_invoice(owner: Browser, bid: str, **fields: Any) -> dict[str, Any]:
    doc = await draft(owner, bid, **fields)
    issued: dict[str, Any] = (await issue(owner, bid, doc["id"])).json()
    return issued


async def make_receipt(
    owner: Browser, bid: str, amount: str, allocations: list[dict[str, str]]
) -> Any:
    response = await owner.post(
        f"/api/v1/businesses/{bid}/documents", json=receipt_body(amount, allocations)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def get_doc(owner: Browser, bid: str, doc_id: str) -> dict[str, Any]:
    result: dict[str, Any] = (
        await owner.get(f"/api/v1/businesses/{bid}/documents/{doc_id}")
    ).json()
    return result


async def test_receipts_pay_invoices_partially_then_fully(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(owner, bid)  # total 1286.20
        assert (invoice["payment_status"], invoice["balance_due"]) == ("unpaid", "1286.20")

        first = await make_receipt(
            owner, bid, "1000", [{"invoice_id": invoice["id"], "amount": "1000"}]
        )
        assert first["allocations"][0]["invoice_number"] == 1
        await issue(owner, bid, first["id"])
        partial = await get_doc(owner, bid, invoice["id"])
        open_list = (
            await owner.get(f"/api/v1/businesses/{bid}/documents", params={"open_only": "true"})
        ).json()

        second = await make_receipt(
            owner, bid, "286.20", [{"invoice_id": invoice["id"], "amount": "286.20"}]
        )
        await issue(owner, bid, second["id"])
        paid = await get_doc(owner, bid, invoice["id"])
        open_after = (
            await owner.get(f"/api/v1/businesses/{bid}/documents", params={"open_only": "true"})
        ).json()

        assert (partial["payment_status"], partial["balance_due"]) == ("partial", "286.20")
        assert [d["id"] for d in open_list] == [invoice["id"]]
        assert open_list[0]["balance_due"] == "286.20"
        assert (paid["payment_status"], paid["amount_paid"], paid["balance_due"]) == (
            "paid",
            "1286.20",
            "0.00",
        )
        assert open_after == []
        assert [(r["relation"], r["direction"], r["amount"]) for r in paid["related"]] == [
            ("pays", "incoming", "1000.00"),
            ("pays", "incoming", "286.20"),
        ]


async def test_receipt_cannot_pay_more_than_the_open_balance(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(owner, bid)

        receipt = await make_receipt(
            owner, bid, "2000", [{"invoice_id": invoice["id"], "amount": "1500"}]
        )
        response = await issue(owner, bid, receipt["id"])

        assert response.json()["error"]["code"] == "allocation_exceeds_balance"
        assert response.json()["error"]["details"]["balance"] == "1286.20"
        assert (await get_doc(owner, bid, invoice["id"]))["payment_status"] == "unpaid"


async def test_allocations_cannot_exceed_the_receipt(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(owner, bid)

        receipt = await make_receipt(
            owner, bid, "100", [{"invoice_id": invoice["id"], "amount": "200"}]
        )

        assert (await issue(owner, bid, receipt["id"])).json()["error"][
            "code"
        ] == "allocations_exceed_receipt"


async def test_allocation_rules(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        base = f"/api/v1/businesses/{bid}/documents"
        draft_invoice = await draft(owner, bid)
        invoice = await issued_invoice(owner, bid)

        to_draft = await owner.post(
            base, json=receipt_body("10", [{"invoice_id": draft_invoice["id"], "amount": "10"}])
        )
        twice = await owner.post(
            base,
            json=receipt_body(
                "20",
                [
                    {"invoice_id": invoice["id"], "amount": "10"},
                    {"invoice_id": invoice["id"], "amount": "10"},
                ],
            ),
        )
        on_quote = await owner.post(
            base,
            json={
                "type": "quote",
                "customer": CUSTOMER,
                "lines": [{"description": "x", "unit_price": "1"}],
                "allocations": [{"invoice_id": invoice["id"], "amount": "1"}],
            },
        )

        assert to_draft.json()["error"]["code"] == "allocation_invalid_invoice"
        assert twice.json()["error"]["code"] == "allocation_duplicate"
        assert on_quote.json()["error"]["code"] == "allocations_not_allowed"


async def test_two_receipts_at_once_cannot_overpay(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(owner, bid)
        full = [{"invoice_id": invoice["id"], "amount": "1286.20"}]
        a = await make_receipt(owner, bid, "1286.20", full)
        b = await make_receipt(owner, bid, "1286.20", full)

        results = await asyncio.gather(issue(owner, bid, a["id"]), issue(owner, bid, b["id"]))

        assert sorted(r.status_code for r in results) == [200, 422]
        assert (await get_doc(owner, bid, invoice["id"]))["amount_paid"] == "1286.20"


async def test_credit_notes_and_invoice_receipts_affect_payment_status(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(owner, bid)
        base = f"/api/v1/businesses/{bid}/documents"
        credit = (await owner.post(f"{base}/{invoice['id']}/credit-note")).json()
        await issue(owner, bid, credit["id"])
        invoice_receipt = await issued_invoice(
            owner,
            bid,
            type="tax_invoice_receipt",
            payments=[{"method": "cash", "amount": "1286.20", "payment_date": today().isoformat()}],
        )

        credited = await get_doc(owner, bid, invoice["id"])

        assert (
            credited["payment_status"],
            credited["amount_credited"],
            credited["balance_due"],
        ) == ("paid", "1286.20", "0.00")
        assert invoice_receipt["payment_status"] == "paid"
