"""Allocation numbers, against a fake tax authority."""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.jobs import worker
from app.services import allocation, ita_client
from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import draft, issue, setup
from tests.test_notifications import Jobs, team

BIG = [{"description": "פרויקט", "quantity": "1", "unit_price": "6000"}]


class FakeIta:
    """Answers the OAuth and Approval calls; ``outage`` / ``refuse`` change its mood."""

    def __init__(self) -> None:
        self.outage = False
        self.refuse = False
        self.approvals: list[dict[str, Any]] = []
        self.next_number = 100000001

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.outage:
            return httpx.Response(503)
        path = request.url.path
        if path.endswith("/longtimetoken/oauth2/token"):
            form = parse_qs(request.content.decode())
            assert form["grant_type"][0] in ("authorization_code", "refresh_token")
            return httpx.Response(
                200,
                json={
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 7776000,
                },
            )
        if path.endswith("/Invoices/v2/Approval"):
            assert request.headers["Authorization"] == "Bearer access-1"
            body = json.loads(request.content)
            self.approvals.append(body)
            if self.refuse:
                return httpx.Response(
                    400, json={"Status": 400, "Message": "Customer is not a registered dealer"}
                )
            number = self.next_number
            self.next_number += 1
            return httpx.Response(
                200, json={"Status": 200, "Message": "Approved", "Confirmation_Number": str(number)}
            )
        return httpx.Response(404)


@pytest.fixture
def ita(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeIta]:
    fake = FakeIta()
    settings = get_settings()
    monkeypatch.setattr(settings, "ita_allocation_enabled", True)
    monkeypatch.setattr(settings, "ita_client_id", "software-1")
    monkeypatch.setattr(settings, "ita_client_secret", "secret-1")
    monkeypatch.setattr(settings, "ita_token_key", Fernet.generate_key().decode())
    monkeypatch.setattr(
        ita_client,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)),
    )
    yield fake


async def connect(owner: Browser, bid: str) -> None:
    started = await owner.post(f"/api/v1/businesses/{bid}/ita/connect")
    assert started.status_code == 200, started.text
    url = urlsplit(started.json()["url"])
    assert url.path.endswith("/tsandbox/longtimetoken/oauth2/authorize")
    query = parse_qs(url.query)
    assert query["client_id"] == ["software-1"]
    assert query["redirect_uri"] == [f"{get_settings().public_url}/api/v1/ita/callback"]
    back = await owner.get(
        "/api/v1/ita/callback", params={"state": query["state"][0], "code": "code-1"}
    )
    assert back.status_code == 303
    assert back.headers["location"] == "/settings?tab=ita&ita=connected"


def test_threshold_follows_the_schedule() -> None:
    assert allocation.threshold(date(2024, 1, 1)) is None
    assert allocation.threshold(date(2025, 6, 1)) == Decimal("20000")
    assert allocation.threshold(date(2026, 3, 1)) == Decimal("10000")
    assert allocation.threshold(date(2026, 6, 1)) == Decimal("5000")


async def test_off_until_configured(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        state = (await owner.get(f"/api/v1/businesses/{bid}/ita")).json()
        assert (state["enabled"], state["connected"]) == (False, False)
        refused = await owner.post(f"/api/v1/businesses/{bid}/ita/connect")
        assert refused.json()["error"]["code"] == "ita_not_configured"
        # Big invoices issue as before, with no number.
        invoice = await draft(owner, bid, lines=BIG)
        issued = (await issue(owner, bid, invoice["id"])).json()
        assert (issued["allocation_number"], issued["allocation_status"]) == (None, None)


async def test_big_invoice_gets_its_number_before_the_pdf(idp: FakeIdP, ita: FakeIta) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await connect(owner, bid)
        state = (await owner.get(f"/api/v1/businesses/{bid}/ita")).json()
        assert (state["enabled"], state["connected"], state["environment"]) == (
            True,
            True,
            "sandbox",
        )

        invoice = await draft(owner, bid, lines=BIG)
        issued = (await issue(owner, bid, invoice["id"])).json()
        assert issued["allocation_number"] == "100000001"
        assert issued["allocation_status"] == "approved"
        [sent] = ita.approvals
        assert sent["Invoice_Type"] == 305
        assert sent["Invoice_Reference_Number"] == str(issued["number"])
        assert sent["Vat_Number"] == 516179157
        assert sent["Customer_VAT_Number"] == 123456782
        assert (sent["Payment_Amount"], sent["VAT_Amount"]) == (6000.0, 1080.0)
        assert sent["Items"][0]["Description"] == "פרויקט"

        # Small invoices, and invoices to private customers, need no number.
        small = await draft(owner, bid)
        assert (await issue(owner, bid, small["id"])).json()["allocation_status"] is None
        private = await draft(owner, bid, lines=BIG, customer={"name": "ישראל ישראלי"})
        assert (await issue(owner, bid, private["id"])).json()["allocation_status"] is None
        assert len(ita.approvals) == 1


async def test_outage_stops_issuing_unless_asked_then_retries(
    idp: FakeIdP, ita: FakeIta, sent_jobs: Jobs
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await connect(owner, bid)
        invoice = await draft(owner, bid, lines=BIG)
        base = f"/api/v1/businesses/{bid}/documents/{invoice['id']}"

        ita.outage = True
        stopped = await issue(owner, bid, invoice["id"])
        assert stopped.status_code == 409
        assert stopped.json()["error"]["code"] == "allocation_failed"
        assert (await owner.get(base)).json()["status"] == "draft"  # nothing was issued

        issued = await owner.post(f"{base}/issue?without_allocation=true")
        assert issued.status_code == 200, issued.text
        assert issued.json()["allocation_status"] == "pending"
        [job] = [kwargs for name, kwargs in sent_jobs if name == "retry_allocation"]

        ita.outage = False
        result = await worker.retry_allocation({"job_try": 1}, **job)
        assert result == "approved"
        after = (await owner.get(base)).json()
        assert (after["allocation_number"], after["allocation_status"]) == ("100000001", "approved")


async def test_refusal_is_reported_and_can_be_retried(idp: FakeIdP, ita: FakeIta) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await connect(owner, bid)
        invoice = await draft(owner, bid, lines=BIG)
        base = f"/api/v1/businesses/{bid}/documents/{invoice['id']}"

        ita.refuse = True
        refused = await issue(owner, bid, invoice["id"])
        assert refused.json()["error"]["code"] == "allocation_rejected"
        issued = await owner.post(f"{base}/issue?without_allocation=true")
        assert issued.json()["allocation_status"] == "rejected"

        ita.refuse = False
        again = await owner.post(f"{base}/allocation")
        assert again.json()["allocation_number"] == "100000001"


async def test_issuing_says_when_the_business_is_not_connected(idp: FakeIdP, ita: FakeIta) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await draft(owner, bid, lines=BIG)
        stopped = await issue(owner, bid, invoice["id"])
        assert stopped.json()["error"]["code"] == "ita_not_connected"
        assert ita.approvals == []


async def test_only_managers_connect(idp: FakeIdP, ita: FakeIta, sent_jobs: Jobs) -> None:
    async with team(idp, sent_jobs) as (_, _owner, bid, member, _accountant):
        refused = await member.post(f"/api/v1/businesses/{bid}/ita/connect")
        assert refused.status_code == 403
