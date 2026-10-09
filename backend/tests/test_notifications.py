import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.jobs import worker
from app.services.documents import today
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import Browser, app_client, second_client
from tests.test_delivery import email_jobs, run_job
from tests.test_delivery import issued as issued_with_email
from tests.test_documents import draft, issue, setup
from tests.test_mcp import call_tool
from tests.test_members import invite_and_join
from tests.test_payments import issued_invoice, make_receipt

Jobs = list[tuple[str, dict[str, Any]]]


async def dispatch() -> int:
    return await worker.dispatch_outbox({})


async def inbox(user: Browser, bid: str, **params: str) -> list[dict[str, Any]]:
    response = await user.get(f"/api/v1/businesses/{bid}/notifications", params=params)
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()
    return result


def notification_emails(jobs: Jobs) -> list[dict[str, Any]]:
    return [kwargs for name, kwargs in jobs if name == "send_email"]


@asynccontextmanager
async def team(
    idp: FakeIdP, jobs: Jobs
) -> AsyncIterator[tuple[Any, Browser, str, Browser, Browser]]:
    """An owner, a member and an accountant, each in their own browser."""
    async with (
        app_client() as client,
        second_client(client) as member_client,
        second_client(client) as cpa_client,
    ):
        owner, bid = await setup(client, idp)
        member = await invite_and_join(
            member_client, idp, owner, bid, jobs, FakeUser(email="dana@example.com"), "member"
        )
        accountant = await invite_and_join(
            cpa_client, idp, owner, bid, jobs, FakeUser(email="cpa@example.com"), "accountant"
        )
        await dispatch()  # the two "joined" notifications
        await owner.post(f"/api/v1/businesses/{bid}/notifications/read", json={})
        yield client, owner, bid, member, accountant


async def test_payment_received_reaches_managers_and_accountant_not_the_actor(
    idp: FakeIdP, sent_jobs: Jobs
) -> None:
    async with team(idp, sent_jobs) as (_, owner, bid, member, accountant):
        invoice = await issued_invoice(member, bid)
        await dispatch()  # "document issued" by the member → the owner only
        receipt = await make_receipt(
            member, bid, "1000", [{"invoice_id": invoice["id"], "amount": "1000"}]
        )
        await issue(member, bid, receipt["id"])
        sent_jobs.clear()

        handled = await dispatch()
        owner_inbox = await inbox(owner, bid, unread_only="true")
        cpa_inbox = await inbox(accountant, bid, unread_only="true")
        member_inbox = await inbox(member, bid)
        count = (await owner.get(f"/api/v1/businesses/{bid}/notifications/unread-count")).json()

        assert handled == 1
        assert [n["event"] for n in owner_inbox] == ["payment_received", "document_issued"]
        payment = owner_inbox[0]
        assert payment["title"] == "התקבל תשלום"  # no amounts or names in the title
        assert payment["body"] == "קבלה מס׳ 1 מלקוח בע״מ: 1,000.00 ₪"
        assert payment["link"] == f"/documents/{receipt['id']}"
        assert payment["read_at"] is None
        assert "הופק על ידי" in owner_inbox[1]["body"]
        assert [n["event"] for n in cpa_inbox] == ["payment_received"]
        assert member_inbox == []  # the member did it themselves
        assert count == {"unread": 2}
        assert notification_emails(sent_jobs) == []  # email is off by default for payments


async def test_ai_actions_notify_the_user_they_acted_for(idp: FakeIdP) -> None:
    owner_user = FakeUser(email="owner@example.com")
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await issued_invoice(owner, bid)  # done by the owner in the app: not news to them
        doc = await draft(owner, bid)
        token = idp.access_token(owner_user, mfa=True)
        await call_tool(
            client,
            token,
            "issue_document",
            {"business_id": bid, "document_id": doc["id"], "confirm": True},
        )

        await dispatch()
        items = await inbox(owner, bid)
        listed = await call_tool(client, token, "list_notifications", {"business_id": bid})
        left = await call_tool(client, token, "mark_notifications_read", {"business_id": bid})

        assert [n["title"] for n in items] == ["הופק מסמך חדש על ידי עוזר AI"]
        assert "חשבונית מס מס׳ 2" in items[0]["body"]
        assert len(listed["structuredContent"]["result"]) == 1
        assert left["structuredContent"]["result"] == 0


async def test_overdue_invoices_notify_once_and_email_by_default(
    idp: FakeIdP, sent_jobs: Jobs
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        late = await issued_invoice(
            owner,
            bid,
            issue_date=(today() - timedelta(days=20)).isoformat(),
            due_date=(today() - timedelta(days=3)).isoformat(),
        )
        paid = await issued_invoice(
            owner,
            bid,
            issue_date=(today() - timedelta(days=15)).isoformat(),
            due_date=(today() - timedelta(days=2)).isoformat(),
        )
        receipt = await make_receipt(
            owner, bid, paid["total"], [{"invoice_id": paid["id"], "amount": paid["total"]}]
        )
        await issue(owner, bid, receipt["id"])
        old = await issued_invoice(owner, bid, due_date=(today() + timedelta(days=5)).isoformat())
        await dispatch()
        sent_jobs.clear()

        raised = await worker.raise_overdue_events({})
        again = await worker.raise_overdue_events({})
        items = await inbox(owner, bid)

        assert (raised, again) == (1, 0)  # only the unpaid one, and only once
        overdue = [n for n in items if n["event"] == "invoice_overdue"]
        assert len(overdue) == 1
        assert overdue[0]["link"] == f"/documents/{late['id']}"
        assert "יתרה 1,286.20 ₪" in overdue[0]["body"]
        assert old["id"] not in {n["link"].rsplit("/", 1)[-1] for n in items}
        emails = notification_emails(sent_jobs)
        assert [e["to"] for e in emails] == ["owner@example.com"]
        assert emails[0]["subject"].startswith("חשבונית לא שולמה במועד")
        assert "₪" not in emails[0]["html"]  # amounts stay in the app
        assert f"/documents/{late['id']}" in emails[0]["text"]


async def test_failed_customer_email_tells_the_sender(
    idp: FakeIdP, sent_jobs: Jobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_smtp(message: EmailMessage) -> None:
        raise ConnectionError("mail server unreachable")

    monkeypatch.setattr(worker, "_smtp_send", broken_smtp)
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        doc = await issued_with_email(owner, bid)
        await owner.post(
            f"/api/v1/businesses/{bid}/documents/{doc['id']}/send-email",
            json={"to": ["a@client.example"], "subject": "x", "message": ""},
        )
        await run_job(email_jobs(sent_jobs)[0], attempt=worker.MAX_TRIES)

        await dispatch()
        items = await inbox(owner, bid)

        assert [n["event"] for n in items] == ["email_failed"]
        assert "a@client.example" in items[0]["body"]


async def test_member_joined_and_inbox_is_private(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client, second_client(client) as member_client:
        owner, bid = await setup(client, idp)
        member = await invite_and_join(
            member_client, idp, owner, bid, sent_jobs, FakeUser(email="dana@example.com"), "member"
        )
        await dispatch()
        owner_items = await inbox(owner, bid)

        member_view = await member.post(
            f"/api/v1/businesses/{bid}/notifications/read",
            json={"ids": [owner_items[0]["id"]]},
        )
        still_unread = await inbox(owner, bid, unread_only="true")
        marked = await owner.post(
            f"/api/v1/businesses/{bid}/notifications/read", json={"ids": [owner_items[0]["id"]]}
        )

        assert [n["event"] for n in owner_items] == ["member_joined"]
        assert owner_items[0]["body"] == "Test User קיבל/ה את ההזמנה והצטרף/ה לעסק."
        assert await inbox(member, bid) == []
        assert member_view.json() == {"unread": 0}  # nothing of the owner's was touched
        assert len(still_unread) == 1
        assert marked.json() == {"unread": 0}


async def test_preferences_choose_channels(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with team(idp, sent_jobs) as (_, owner, bid, member, _cpa):
        defaults = (await owner.get("/api/v1/me/notification-preferences")).json()
        saved = await owner.put(
            "/api/v1/me/notification-preferences",
            json={
                "preferences": {
                    "payment_received": {"in_app": False, "email": True},
                    "document_issued": {"in_app": False, "email": False},
                }
            },
        )
        invoice = await issued_invoice(member, bid)
        receipt = await make_receipt(
            member, bid, "100", [{"invoice_id": invoice["id"], "amount": "100"}]
        )
        await issue(member, bid, receipt["id"])
        sent_jobs.clear()

        await dispatch()

        assert {p["event"]: p["channels"] for p in defaults}["invoice_overdue"] == {
            "in_app": True,
            "email": True,
            "push": True,
        }
        assert saved.status_code == 200
        assert await inbox(owner, bid, unread_only="true") == []
        assert [e["to"] for e in notification_emails(sent_jobs)] == ["owner@example.com"]


async def test_concurrent_dispatchers_handle_each_event_once(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        token = idp.access_token(FakeUser(email="owner@example.com"), mfa=True)
        for _ in range(4):
            doc = await draft(owner, bid)
            await call_tool(
                client,
                token,
                "issue_document",
                {"business_id": bid, "document_id": doc["id"], "confirm": True},
            )

        results = await asyncio.gather(dispatch(), dispatch(), dispatch())
        items = await inbox(owner, bid)

    assert sum(results) == 4
    assert len(items) == 4


async def test_database_only_lets_members_receive_notifications(idp: FakeIdP) -> None:
    async with app_client() as client:
        _, bid = await setup(client, idp)
    engine = create_async_engine(get_settings().database_url)  # the restricted app role
    stranger = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(DBAPIError, match="row-level security"):
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.business_id', :b, true)"), {"b": bid})
            await conn.execute(
                text(
                    "INSERT INTO notifications (id, user_id, business_id, event, title, body, "
                    "link, dedupe_key) VALUES (gen_random_uuid(), :u, :b, 'x', 't', '', '', 'k')"
                ),
                {"u": stranger, "b": bid},
            )
    async with engine.begin() as conn:
        # Inside the business but without being a user: no one's notifications are visible.
        await conn.execute(text("SELECT set_config('app.business_id', :b, true)"), {"b": bid})
        visible = (await conn.execute(text("SELECT count(*) FROM notifications"))).scalar_one()
    await engine.dispose()
    assert visible == 0
