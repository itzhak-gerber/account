import base64
from email.message import EmailMessage
from typing import Any

import pytest
from arq import Retry

from app.jobs import worker
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import Browser, app_client
from tests.test_branding import png, upload
from tests.test_documents import CUSTOMER, draft, issue, setup
from tests.test_mcp import call_tool
from tests.test_members import invite_and_join

CUSTOMER_WITH_EMAIL = {**CUSTOMER, "email": "billing@client.example"}


async def issued(owner: Browser, bid: str) -> dict[str, Any]:
    doc = await draft(owner, bid, customer=CUSTOMER_WITH_EMAIL)
    result: dict[str, Any] = (await issue(owner, bid, doc["id"])).json()
    return result


def email_jobs(jobs: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [kwargs for name, kwargs in jobs if name == "send_document_email"]


async def test_defaults_use_customer_email_and_hebrew_text(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued(owner, bid)

        defaults = (
            await owner.get(f"/api/v1/businesses/{bid}/documents/{doc['id']}/email-defaults")
        ).json()

        assert defaults["to"] == ["billing@client.example"]
        assert defaults["subject"] == "חשבונית מס מס׳ 1 מאת דוגמה בע״מ"
        assert "מצ״ב חשבונית מס מס׳ 1" in defaults["message"]


async def test_send_queues_email_with_original_then_copy(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued(owner, bid)
        url = f"/api/v1/businesses/{bid}/documents/{doc['id']}/send-email"
        body = {"to": ["a@client.example"], "subject": "חשבונית", "message": "שלום\n\nמצורף"}

        first = await owner.post(url, json=body)
        second = await owner.post(url, json={**body, "to": ["b@client.example", "c@x.example"]})
        view = (await owner.get(f"/api/v1/businesses/{bid}/documents/{doc['id']}")).json()
        log = (await owner.get(f"/api/v1/businesses/{bid}/audit-log")).json()

        assert first.status_code == 202, first.text
        assert (first.json()["status"], first.json()["variant"]) == ("queued", "original")
        assert second.json()["variant"] == "copy"
        jobs = email_jobs(sent_jobs)
        assert [j["to"] for j in jobs] == [
            ["a@client.example"],
            ["b@client.example", "c@x.example"],
        ]
        assert base64.b64decode(jobs[0]["attachment_b64"]).startswith(b"%PDF")
        assert jobs[0]["attachment_name"] == "חשבונית מס 1.pdf"
        assert "שלום" in jobs[0]["html"] and 'dir="rtl"' in jobs[0]["html"]
        assert [d["recipients"] for d in view["deliveries"]] == [
            ["b@client.example", "c@x.example"],
            ["a@client.example"],
        ]
        assert [e["action"] for e in log].count("document.emailed") == 2


async def test_send_rules(idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued(owner, bid)
        a_draft = await draft(owner, bid)
        base = f"/api/v1/businesses/{bid}/documents"
        ok = {"subject": "x", "message": ""}

        not_issued = await owner.post(
            f"{base}/{a_draft['id']}/send-email", json={**ok, "to": ["a@x.example"]}
        )
        bad_email = await owner.post(
            f"{base}/{doc['id']}/send-email", json={**ok, "to": ["not-an-email"]}
        )
        too_many = await owner.post(
            f"{base}/{doc['id']}/send-email",
            json={**ok, "to": [f"u{i}@x.example" for i in range(6)]},
        )
        accountant = await invite_and_join(
            client, idp, owner, bid, sent_jobs, FakeUser(email="acc@example.com"), "accountant"
        )
        forbidden = await accountant.post(
            f"{base}/{doc['id']}/send-email", json={**ok, "to": ["a@x.example"]}
        )

        assert not_issued.json()["error"]["code"] == "document_not_issued"
        assert bad_email.status_code == 422
        assert too_many.status_code == 422
        assert forbidden.status_code == 403
        assert email_jobs(sent_jobs) == []


async def run_job(job: dict[str, Any], *, attempt: int = 1) -> None:
    await worker.send_document_email({"job_try": attempt}, **job)


async def test_worker_sends_pdf_and_inline_logo_and_records_sent(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[EmailMessage] = []

    async def fake_smtp(message: EmailMessage) -> None:
        sent.append(message)

    monkeypatch.setattr(worker, "_smtp_send", fake_smtp)
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await upload(owner, bid, png())
        doc = await issued(owner, bid)
        await owner.post(
            f"/api/v1/businesses/{bid}/documents/{doc['id']}/send-email",
            json={"to": ["a@client.example"], "subject": "חשבונית מס 1", "message": "שלום"},
        )

        await run_job(email_jobs(sent_jobs)[0])
        view = (await owner.get(f"/api/v1/businesses/{bid}/documents/{doc['id']}")).json()

    message = sent[0]
    parts = [(p.get_content_type(), p.get_filename()) for p in message.walk()]
    assert ("application/pdf", "חשבונית מס 1.pdf") in parts
    assert ("image/png", None) in parts
    assert message["To"] == "a@client.example"
    assert view["deliveries"][0]["status"] == "sent"
    assert view["deliveries"][0]["sent_at"] is not None


async def test_worker_records_failures_and_retries(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_smtp(message: EmailMessage) -> None:
        raise ConnectionError("mail server unreachable")

    monkeypatch.setattr(worker, "_smtp_send", broken_smtp)
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued(owner, bid)
        await owner.post(
            f"/api/v1/businesses/{bid}/documents/{doc['id']}/send-email",
            json={"to": ["a@client.example"], "subject": "x", "message": ""},
        )
        job = email_jobs(sent_jobs)[0]

        with pytest.raises(Retry):
            await run_job(job, attempt=1)
        await run_job(job, attempt=worker.MAX_TRIES)  # last attempt: no more retries
        delivery = (await owner.get(f"/api/v1/businesses/{bid}/documents/{doc['id']}")).json()[
            "deliveries"
        ][0]

    assert delivery["status"] == "failed"
    assert "unreachable" in delivery["error"]


async def test_mcp_send_needs_confirmation(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    owner_user = FakeUser(email="owner@example.com")
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued(owner, bid)
        token = idp.access_token(owner_user, mfa=True)
        args = {"business_id": bid, "document_id": doc["id"]}

        preview = await call_tool(client, token, "send_document_email", args)
        sent = await call_tool(client, token, "send_document_email", {**args, "confirm": True})

        assert preview["isError"] is True
        assert "billing@client.example" in preview["content"][0]["text"]
        assert sent["structuredContent"]["recipients"] == ["billing@client.example"]
        assert len(email_jobs(sent_jobs)) == 1
