import base64
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import get_settings
from app.jobs import worker
from app.services import push
from tests.fake_idp import FakeIdP
from tests.helpers import Browser, app_client
from tests.test_documents import issue, setup
from tests.test_notifications import Jobs, dispatch, team
from tests.test_payments import issued_invoice, make_receipt

FCM = "https://fcm.googleapis.com/fcm/send/abc123"
APPLE = "https://web.push.apple.com/QGuQyavXutnMH"
KEYS = {
    "p256dh": (
        "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
    ),
    "auth": "tBHItJI5svbpez7KI4CCXg",
}


@pytest.fixture
def vapid(monkeypatch: pytest.MonkeyPatch) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    encoded = base64.urlsafe_b64encode(der).rstrip(b"=").decode()
    monkeypatch.setattr(get_settings(), "vapid_private_key", encoded)
    return encoded


def push_jobs(jobs: Jobs) -> list[dict[str, Any]]:
    return [kwargs for name, kwargs in jobs if name == "send_push"]


async def user_id(user: Browser) -> str:
    me: dict[str, Any] = (await user.get("/api/v1/me")).json()
    return str(me["user"]["id"])


async def devices(user: Browser) -> int:
    response = await user.get("/api/v1/me/push")
    assert response.status_code == 200, response.text
    return int(response.json()["devices"])


def test_only_known_push_services_are_accepted() -> None:
    assert push.endpoint_allowed(FCM)
    assert push.endpoint_allowed(APPLE)
    assert push.endpoint_allowed("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert push.endpoint_allowed("https://wns2-db5p.notify.windows.com/w/?token=x")
    assert not push.endpoint_allowed("http://fcm.googleapis.com/fcm/send/x")  # not https
    assert not push.endpoint_allowed("https://evil.example.com/fcm.googleapis.com")
    assert not push.endpoint_allowed("https://fcm.googleapis.com.evil.example/x")
    assert not push.endpoint_allowed("https://169.254.169.254/latest")


async def test_subscribe_test_and_unsubscribe(idp: FakeIdP, sent_jobs: Jobs, vapid: str) -> None:
    async with app_client() as client:
        owner, _bid = await setup(client, idp)
        config = (await owner.get("/api/v1/me/push")).json()
        assert config == {"public_key": push.public_key(), "devices": 0}
        assert len(base64.urlsafe_b64decode(config["public_key"] + "==")) == 65

        assert (
            await owner.put("/api/v1/me/push", json={"endpoint": FCM, "keys": KEYS})
        ).status_code == 204
        # The same device again only refreshes its keys.
        assert (
            await owner.put("/api/v1/me/push", json={"endpoint": FCM, "keys": KEYS})
        ).status_code == 204
        assert await devices(owner) == 1

        refused = await owner.put(
            "/api/v1/me/push", json={"endpoint": "https://attacker.example/x", "keys": KEYS}
        )
        assert refused.status_code == 400
        assert refused.json()["error"]["code"] == "push_endpoint_not_allowed"

        sent_jobs.clear()
        assert (await owner.post("/api/v1/me/push/test")).status_code == 202
        [job] = push_jobs(sent_jobs)
        assert job["user_ids"] == [await user_id(owner)]
        assert job["link"] == "/profile"

        await owner.post("/api/v1/me/push/unsubscribe", json={"endpoint": FCM})
        assert await devices(owner) == 0


async def test_no_push_without_a_server_key(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client:
        owner, _bid = await setup(client, idp)
        assert (await owner.get("/api/v1/me/push")).json()["public_key"] is None
        sent_jobs.clear()
        await owner.post("/api/v1/me/push/test")
        assert push_jobs(sent_jobs) == []


async def test_payment_is_pushed_to_managers_and_accountant(
    idp: FakeIdP, sent_jobs: Jobs, vapid: str
) -> None:
    async with team(idp, sent_jobs) as (_, owner, bid, member, accountant):
        invoice = await issued_invoice(member, bid)
        await dispatch()
        receipt = await make_receipt(
            member, bid, "1000", [{"invoice_id": invoice["id"], "amount": "1000"}]
        )
        await issue(member, bid, receipt["id"])
        sent_jobs.clear()
        await dispatch()

        [job] = push_jobs(sent_jobs)
        assert sorted(job["user_ids"]) == sorted([await user_id(owner), await user_id(accountant)])
        # Only the title travels to the lock screen: no amounts or customer names.
        assert job["title"] == "התקבל תשלום"
        assert job["link"] == f"/documents/{receipt['id']}"


async def test_worker_sends_and_forgets_devices_that_are_gone(
    idp: FakeIdP, vapid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with app_client() as client:
        owner, _bid = await setup(client, idp)
        for endpoint in (FCM, APPLE):
            await owner.put("/api/v1/me/push", json={"endpoint": endpoint, "keys": KEYS})
        delivered: list[tuple[str, str]] = []

        def fake_send(subscription: dict[str, Any], data: str) -> int:
            delivered.append((subscription["endpoint"], data))
            return 410 if subscription["endpoint"] == APPLE else 201

        monkeypatch.setattr(push, "send_one", fake_send)
        sent = await worker.send_push(
            {}, user_ids=[await user_id(owner)], title="התקבל תשלום", link="/documents/x", tag="t"
        )

        assert sent == 1
        assert sorted(e for e, _ in delivered) == sorted([FCM, APPLE])
        assert '"title": "התקבל תשלום"' in delivered[0][1]
        assert await devices(owner) == 1  # the Apple device reported "gone" and was forgotten


def test_real_encryption_and_vapid_signature(vapid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """pywebpush accepts our key format; the request is encrypted and signed (not sent)."""
    import requests

    captured: dict[str, Any] = {}

    class Response:
        status_code = 201
        text = ""
        headers: dict[str, str] = {}  # noqa: RUF012

    def fake_post(url: str, data: bytes, headers: dict[str, str], **_: Any) -> Response:
        captured.update(url=url, data=data, headers=headers)
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)
    status = push.send_one(
        {"endpoint": FCM, "keys": KEYS}, push.payload(title="שלום", link="/", tag="t")
    )

    assert status == 201
    assert captured["url"] == FCM
    assert captured["headers"]["Content-Encoding"] == "aes128gcm"
    assert captured["headers"]["Authorization"].startswith("vapid t=")
    assert f"k={push.public_key()}" in captured["headers"]["Authorization"]
    assert "שלום".encode() not in captured["data"]  # the payload is encrypted
