import asyncio
import os
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.documents import today
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import VALID_BUSINESS, Browser, app_client, browser_login
from tests.test_members import invite_and_join

BUSINESS = {**VALID_BUSINESS, "address_street": "הרצל 1", "address_city": "תל אביב"}
CUSTOMER = {"name": "לקוח בע״מ", "tax_id": "123456782", "address_city": "חיפה"}
LINES = [
    {"description": "ייעוץ", "quantity": "2", "unit_price": "500"},
    {"description": "נסיעות", "quantity": "1", "unit_price": "100", "discount_percent": "10"},
]


async def setup(client: AsyncClient, idp: FakeIdP, **business: object) -> tuple[Browser, str]:
    owner = await browser_login(client, idp, FakeUser(email="owner@example.com"), mfa=True)
    created = await owner.post("/api/v1/businesses", json={**BUSINESS, **business})
    assert created.status_code == 201, created.text
    return owner, created.json()["business"]["id"]


async def draft(owner: Browser, bid: str, **fields: Any) -> dict[str, Any]:
    body = {"type": "tax_invoice", "customer": CUSTOMER, "lines": LINES, **fields}
    response = await owner.post(f"/api/v1/businesses/{bid}/documents", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def issue(owner: Browser, bid: str, doc_id: str) -> Any:
    return await owner.post(f"/api/v1/businesses/{bid}/documents/{doc_id}/issue")


async def test_tax_invoice_draft_computes_vat(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)

        doc = await draft(owner, bid)

        assert doc["status"] == "draft"
        assert doc["number"] is None
        assert doc["title"] == "חשבונית מס"
        assert doc["vat_rate"] == "0.1800"
        assert [line["line_total"] for line in doc["lines"]] == ["1000.00", "90.00"]
        assert (doc["subtotal"], doc["vat_amount"], doc["total"]) == (
            "1090.00",
            "196.20",
            "1286.20",
        )


async def test_issue_assigns_gapless_numbers_and_freezes(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        base = f"/api/v1/businesses/{bid}/documents"
        first, second = await draft(owner, bid), await draft(owner, bid)

        issued_first = await issue(owner, bid, first["id"])
        issued_second = await issue(owner, bid, second["id"])
        again = await issue(owner, bid, first["id"])
        edit = await owner.patch(f"{base}/{first['id']}", json={"notes": "x"})
        delete = await owner.delete(f"{base}/{first['id']}")

        assert issued_first.status_code == 200, issued_first.text
        assert issued_first.json()["number"] == 1
        assert issued_second.json()["number"] == 2
        assert issued_first.json()["status"] == "issued"
        assert again.json()["error"]["code"] == "document_issued"
        assert edit.json()["error"]["code"] == "document_issued"
        assert delete.json()["error"]["code"] == "document_issued"
        log = [e["action"] for e in (await owner.get(f"/api/v1/businesses/{bid}/audit-log")).json()]
        assert log.count("document.issued") == 2


async def test_database_refuses_to_change_issued_documents(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await draft(owner, bid)
        await issue(owner, bid, doc["id"])

    engine = create_async_engine(os.environ["APP_TEST_ADMIN_DATABASE_URL"])
    for statement in (
        "UPDATE documents SET total = 1 WHERE id = :id",
        "DELETE FROM documents WHERE id = :id",
        "UPDATE document_lines SET unit_price = 1 WHERE document_id = :id",
    ):
        async with engine.begin() as conn:
            with pytest.raises(Exception, match="cannot be"):
                await conn.execute(text(statement), {"id": doc["id"]})
    await engine.dispose()


async def test_concurrent_issues_get_distinct_consecutive_numbers(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        drafts = [await draft(owner, bid) for _ in range(6)]

        results = await asyncio.gather(*(issue(owner, bid, d["id"]) for d in drafts))

        assert sorted(r.json()["number"] for r in results) == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"customer": {"name": ""}}, "customer_name_required"),
        ({"lines": []}, "lines_required"),
        ({"issue_date": (date.today() + timedelta(days=3)).isoformat()}, "issue_date_in_future"),
    ],
)
async def test_issue_validation(idp: FakeIdP, fields: dict[str, Any], code: str) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await draft(owner, bid, **fields)

        response = await issue(owner, bid, doc["id"])

        assert response.status_code == 422
        assert response.json()["error"]["code"] == code


async def test_dates_cannot_go_backwards_and_vat_follows_the_date(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        old = await draft(owner, bid, issue_date="2024-12-31")
        assert old["vat_rate"] == "0.1700"
        assert (await issue(owner, bid, old["id"])).json()["number"] == 1
        current = await draft(owner, bid)
        await issue(owner, bid, current["id"])
        backdated = await draft(owner, bid, issue_date="2025-06-01")

        response = await issue(owner, bid, backdated["id"])

        assert response.json()["error"]["code"] == "issue_date_before_last"


async def test_tax_documents_need_the_business_address(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp, address_street="", address_city="")
        doc = await draft(owner, bid)

        response = await issue(owner, bid, doc["id"])

        assert response.json()["error"]["code"] == "business_address_required"


async def test_receipt_and_invoice_receipt(idp: FakeIdP) -> None:
    payment = {"method": "bank_transfer", "amount": "1286.20", "payment_date": today().isoformat()}
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        receipt = await draft(
            owner,
            bid,
            type="receipt",
            lines=[],
            payments=[{**payment, "amount": "500", "details": {"reference": "123"}}],
        )
        with_lines = await owner.post(
            f"/api/v1/businesses/{bid}/documents",
            json={"type": "receipt", "customer": CUSTOMER, "lines": LINES},
        )
        short = await draft(
            owner, bid, type="tax_invoice_receipt", payments=[{**payment, "amount": "100"}]
        )
        exact = await draft(owner, bid, type="tax_invoice_receipt", payments=[payment])

        assert (receipt["total"], receipt["vat_amount"]) == ("500.00", "0.00")
        assert (await issue(owner, bid, receipt["id"])).json()["number"] == 1
        assert with_lines.json()["error"]["code"] == "lines_not_allowed"
        assert (await issue(owner, bid, short["id"])).json()["error"]["code"] == "payments_mismatch"
        assert (await issue(owner, bid, exact["id"])).json()["number"] == 1


async def test_exempt_dealer_cannot_issue_tax_invoices_and_charges_no_vat(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp, business_type="exempt_dealer", tax_id="123456782")
        types = [
            t["type"] for t in (await owner.get(f"/api/v1/businesses/{bid}/document-types")).json()
        ]
        invoice = await owner.post(
            f"/api/v1/businesses/{bid}/documents",
            json={"type": "tax_invoice", "customer": CUSTOMER, "lines": LINES},
        )
        proforma = await draft(owner, bid, type="proforma_invoice")

        assert types == ["quote", "proforma_invoice", "receipt", "delivery_note"]
        assert invoice.json()["error"]["code"] == "document_type_not_allowed"
        assert (proforma["vat_amount"], proforma["total"]) == ("0.00", "1090.00")


async def test_numbering_can_continue_from_previous_software(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        url = f"/api/v1/businesses/{bid}/numbering"

        assert (
            await owner.client.put(
                url,
                json={"type": "tax_invoice", "next_number": 1001},
                headers={"X-CSRF-Token": owner.csrf},
            )
        ).status_code == 200
        doc = await draft(owner, bid)
        assert (await issue(owner, bid, doc["id"])).json()["number"] == 1001
        locked = await owner.client.put(
            url,
            json={"type": "tax_invoice", "next_number": 5},
            headers={"X-CSRF-Token": owner.csrf},
        )
        assert locked.json()["error"]["code"] == "numbering_locked"
        assert (await owner.get(url)).json()["next_numbers"]["tax_invoice"] == 1002


async def test_quote_converts_to_invoice(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        quote = await draft(owner, bid, type="quote")
        await issue(owner, bid, quote["id"])

        response = await owner.post(
            f"/api/v1/businesses/{bid}/documents/{quote['id']}/convert",
            json={"type": "tax_invoice"},
        )
        invoice = response.json()
        issued = (await issue(owner, bid, invoice["id"])).json()

        assert invoice["status"] == "draft"
        assert invoice["total"] == quote["total"]
        assert issued["related"] == [
            {
                "id": quote["id"],
                "type": "quote",
                "number": 1,
                "status": "issued",
                "relation": "converted_from",
                "amount": None,
                "direction": "outgoing",
            }
        ]


async def test_credit_notes_cannot_exceed_the_invoice(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await draft(owner, bid)
        await issue(owner, bid, invoice["id"])
        base = f"/api/v1/businesses/{bid}/documents"

        direct = await owner.post(
            base, json={"type": "credit_note", "customer": CUSTOMER, "lines": LINES}
        )
        partial = (await owner.post(f"{base}/{invoice['id']}/credit-note")).json()
        partial = (await owner.patch(f"{base}/{partial['id']}", json={"lines": LINES[1:]})).json()
        issued_partial = await issue(owner, bid, partial["id"])
        full = (await owner.post(f"{base}/{invoice['id']}/credit-note")).json()
        too_much = await issue(owner, bid, full["id"])

        assert direct.json()["error"]["code"] == "credit_note_from_invoice"
        assert issued_partial.json()["number"] == 1
        assert issued_partial.json()["total"] == "106.20"
        assert too_much.json()["error"]["code"] == "credit_exceeds_invoice"
        assert too_much.json()["error"]["details"]["remaining"] == "1180.00"


async def test_pdf_original_once_then_copies(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await draft(owner, bid)
        url = f"/api/v1/businesses/{bid}/documents/{doc['id']}/pdf"

        preview = await owner.get(url)
        await issue(owner, bid, doc["id"])
        first, second = await owner.get(url), await owner.get(url)

        assert preview.headers["X-Document-Variant"] == "draft"
        assert first.headers["X-Document-Variant"] == "original"
        assert second.headers["X-Document-Variant"] == "copy"
        assert first.content.startswith(b"%PDF")
        assert first.headers["content-type"] == "application/pdf"


async def test_role_rules_for_documents(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await draft(owner, bid)
        accountant = await invite_and_join(
            client, idp, owner, bid, sent_jobs, FakeUser(email="acc@example.com"), "accountant"
        )
        base = f"/api/v1/businesses/{bid}/documents"

        assert len((await accountant.get(base)).json()) == 1
        assert (await accountant.post(base, json={"type": "quote"})).status_code == 403
        assert (await issue(accountant, bid, doc["id"])).status_code == 403
