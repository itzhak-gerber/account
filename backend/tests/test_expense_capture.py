"""Supplier invoices from a photo or PDF, read by a fake Claude."""

import io
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from app.core.config import get_settings
from app.services import expense_capture
from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import setup
from tests.test_purchasing import supplier

READING = {
    "is_invoice": True,
    "supplier_name": "סיטונאות הצפון",
    "supplier_tax_id": "515555555",
    "invoice_number": "A-7731",
    "invoice_date": "2026-10-06",
    "net_amount": 1000,
    "vat_amount": 180,
    "total": 1180,
}


def photo() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (3000, 4000), (250, 250, 245)).save(out, format="JPEG")
    return out.getvalue()


async def scan(browser: Browser, bid: str, content: bytes, name: str = "invoice.jpg") -> Any:
    return await browser.client.post(
        f"/api/v1/businesses/{bid}/supplier-invoices/scan",
        files={"file": (name, content, "application/octet-stream")},
        headers={"X-CSRF-Token": browser.csrf},
    )


class FakeClaude:
    def __init__(self, reading: dict[str, Any] | None, stop_reason: str = "end_turn") -> None:
        self.reading = reading
        self.stop_reason = stop_reason
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        text = json.dumps(self.reading) if self.reading is not None else ""
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=text),
            ],
        )


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch) -> FakeClaude:
    fake = FakeClaude(READING)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(expense_capture, "_client", lambda: fake)
    return fake


def test_only_checked_values_survive() -> None:
    cleaned = expense_capture.clean({**READING, "net_amount": None, "invoice_date": "06/10/2026"})
    assert cleaned["net_amount"] == Decimal("1000.00")  # worked out from total - VAT
    assert "invoice_date" not in cleaned  # not a valid ISO date
    bad_id = expense_capture.clean({**READING, "supplier_tax_id": "123456789"})
    assert "supplier_tax_id" not in bad_id  # fails the check digit
    assert expense_capture.clean({**READING, "is_invoice": False}) == {}
    assert expense_capture.clean(None) == {}


async def test_photo_is_kept_as_pdf_and_read(idp: FakeIdP, claude: FakeClaude) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        await owner.patch(
            f"/api/v1/businesses/{bid}/suppliers/{north['id']}", json={"tax_id": "515555555"}
        )

        scanned = await scan(owner, bid, photo())
        assert scanned.status_code == 201, scanned.text
        found = scanned.json()
        assert found["read"] is True
        assert found["supplier_id"] == north["id"]  # matched by tax ID
        assert (found["invoice_number"], found["invoice_date"]) == ("A-7731", "2026-10-06")
        assert (found["net_amount"], found["vat_amount"], found["total"]) == (
            "1000.00",
            "180.00",
            "1180.00",
        )

        [request] = claude.requests
        assert request["model"] == "claude-opus-5-5"
        assert request["fallbacks"] == "default"
        assert request["output_config"]["format"]["schema"] == expense_capture.SCHEMA
        image = request["messages"][0]["content"][0]
        assert image["source"]["media_type"] == "image/jpeg"

        base = f"/api/v1/businesses/{bid}/supplier-invoices"
        created = await owner.post(
            base,
            json={
                "supplier_id": north["id"],
                "invoice_number": found["invoice_number"],
                "invoice_date": found["invoice_date"],
                "net_amount": found["net_amount"],
                "vat_amount": found["vat_amount"],
                "file_id": found["file_id"],
            },
        )
        assert created.status_code == 201, created.text
        kept = await owner.get(f"{base}/{created.json()['id']}/file")
        assert kept.headers["content-type"] == "application/pdf"
        assert kept.content.startswith(b"%PDF")


async def test_without_a_key_the_file_is_kept_for_typing(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        scanned = (await scan(owner, bid, b"%PDF-1.7\n%fake\n", "invoice.pdf")).json()
        assert (scanned["read"], scanned["ai_enabled"]) == (False, False)
        assert scanned["file_id"]

        refused = await scan(owner, bid, b"not a picture")
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "invalid_scan"


async def test_a_declined_or_unreadable_reading_suggests_nothing(
    idp: FakeIdP, claude: FakeClaude
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        claude.stop_reason = "refusal"
        assert (await scan(owner, bid, photo())).json()["read"] is False
        claude.stop_reason, claude.reading = "end_turn", {**READING, "is_invoice": False}
        assert (await scan(owner, bid, photo())).json()["read"] is False


async def test_a_file_of_another_business_cannot_be_attached(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        north = await supplier(owner, bid)
        created = await owner.post(
            f"/api/v1/businesses/{bid}/supplier-invoices",
            json={
                "supplier_id": north["id"],
                "invoice_number": "1",
                "invoice_date": "2026-10-06",
                "net_amount": "1",
                "vat_amount": "0",
                "file_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert created.json()["error"]["code"] == "file_not_found"
