from datetime import timedelta
from typing import Any

from app.jobs import worker
from app.services.devices import describe
from app.services.documents import today
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import app_client, browser_login, second_client
from tests.test_documents import issue, setup
from tests.test_members import invite_and_join
from tests.test_notifications import dispatch, inbox, notification_emails
from tests.test_payments import issued_invoice, make_receipt

Jobs = list[tuple[str, dict[str, Any]]]
OWNER = FakeUser(email="owner@example.com")


def test_device_labels() -> None:
    chrome_windows = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
    safari_iphone = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    )
    edge = chrome_windows + " Edg/140.0"
    assert describe(chrome_windows) == "Chrome · Windows"
    assert describe(safari_iphone) == "Safari · iPhone"
    assert describe(edge) == "Edge · Windows"
    assert describe("") == "דפדפן"


async def test_new_device_alerts_but_known_device_does_not(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client, second_client(client) as laptop:
        owner, bid = await setup(client, idp)  # first device ever: recorded silently
        assert notification_emails(sent_jobs) == []
        sent_jobs.clear()

        await browser_login(laptop, idp, OWNER, mfa=True)  # a second browser
        alert_emails = notification_emails(sent_jobs)
        sent_jobs.clear()
        again = await browser_login(laptop, idp, OWNER, mfa=True)  # same browser again
        owner = await browser_login(client, idp, OWNER, mfa=True)  # and the first one
        items = await inbox(owner, bid)
        listed = (await again.get("/api/v1/me/devices")).json()

        assert [n["event"] for n in items] == ["new_device_login"]
        assert items[0]["title"] == "כניסה לחשבון ממכשיר חדש"
        assert items[0]["link"] == "/profile"
        assert [e["to"] for e in alert_emails] == ["owner@example.com"]
        assert alert_emails[0]["subject"] == "כניסה לחשבון ממכשיר חדש"
        assert notification_emails(sent_jobs) == []  # known devices: no more alerts
        assert len(listed) == 2
        assert sum(d["current"] for d in listed) == 1


async def test_device_alert_respects_preferences_and_forget(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client, second_client(client) as phone:
        owner, bid = await setup(client, idp)
        await owner.put(
            "/api/v1/me/notification-preferences",
            json={"preferences": {"new_device_login": {"in_app": True, "email": False}}},
        )
        sent_jobs.clear()
        on_phone = await browser_login(phone, idp, OWNER, mfa=True)
        devices = (await on_phone.get("/api/v1/me/devices")).json()
        phone_device = next(d for d in devices if d["current"])

        forgotten = await on_phone.delete(f"/api/v1/me/devices/{phone_device['id']}")
        await browser_login(phone, idp, OWNER, mfa=True)  # forgotten → new again
        items = await inbox(on_phone, bid)

        assert notification_emails(sent_jobs) == []
        assert forgotten.status_code == 204
        assert [n["event"] for n in items] == ["new_device_login", "new_device_login"]


async def test_cannot_forget_someone_elses_device(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client, second_client(client) as other:
        owner, _ = await setup(client, idp)
        mine = (await owner.get("/api/v1/me/devices")).json()[0]
        stranger = await browser_login(other, idp, FakeUser(email="x@example.com"))

        response = await stranger.delete(f"/api/v1/me/devices/{mine['id']}")

        assert response.status_code == 404
        assert len((await owner.get("/api/v1/me/devices")).json()) == 1


async def test_daily_summary_emails_managers_once(idp: FakeIdP, sent_jobs: Jobs) -> None:
    yesterday = (today() - timedelta(days=1)).isoformat()
    async with app_client() as client, second_client(client) as member_client:
        owner, bid = await setup(client, idp)
        member = await invite_and_join(
            member_client, idp, owner, bid, sent_jobs, FakeUser(email="dana@example.com"), "member"
        )
        invoice = await issued_invoice(owner, bid, issue_date=yesterday)  # 1,286.20
        receipt = await make_receipt(
            owner, bid, "286.20", [{"invoice_id": invoice["id"], "amount": "286.20"}]
        )
        await owner.patch(
            f"/api/v1/businesses/{bid}/documents/{receipt['id']}", json={"issue_date": yesterday}
        )
        await issue(owner, bid, receipt["id"])
        await dispatch()
        sent_jobs.clear()

        raised = await worker.raise_daily_summaries({})
        again = await worker.raise_daily_summaries({})
        emails = notification_emails(sent_jobs)
        owner_items = await inbox(owner, bid, unread_only="true")
        member_items = await inbox(member, bid)

    assert (raised, again) == (1, 0)
    assert [e["to"] for e in emails] == ["owner@example.com"]  # the member gets none
    summary = emails[0]
    assert summary["subject"].startswith("סיכום יומי ל-")
    assert "הכנסות לפני מע״מ" in summary["text"]
    assert "1,090.00 ₪" in summary["text"]  # income before VAT
    assert "286.20 ₪" in summary["text"]  # received
    assert "1,000.00 ₪ (מסמך אחד)" in summary["text"]  # still open
    assert "סיכום הפעילות בעסק" in summary["text"]
    assert "<table" in summary["html"]
    assert all(n["event"] != "daily_summary" for n in owner_items)  # email only by default
    assert all(n["event"] != "daily_summary" for n in member_items)


async def test_no_summary_on_a_quiet_day_with_nothing_owed(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        invoice = await issued_invoice(
            owner, bid, issue_date=(today() - timedelta(days=5)).isoformat()
        )
        receipt = await make_receipt(
            owner,
            bid,
            invoice["total"],
            [{"invoice_id": invoice["id"], "amount": invoice["total"]}],
        )
        await owner.patch(
            f"/api/v1/businesses/{bid}/documents/{receipt['id']}",
            json={"issue_date": (today() - timedelta(days=5)).isoformat()},
        )
        await issue(owner, bid, receipt["id"])
        await dispatch()
        sent_jobs.clear()

        raised = await worker.raise_daily_summaries({})

    assert raised == 1  # the business is checked...
    assert notification_emails(sent_jobs) == []  # ...but there is nothing to tell
