from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import VALID_BUSINESS, Browser, app_client, browser_login

OWNER = FakeUser(email="owner@example.com", name="בעלת העסק")


async def setup_business(client: AsyncClient, idp: FakeIdP) -> tuple[Browser, str]:
    owner = await browser_login(client, idp, OWNER, mfa=True)
    response = await owner.post("/api/v1/businesses", json=VALID_BUSINESS)
    return owner, response.json()["business"]["id"]


def token_from(job: tuple[str, dict[str, Any]]) -> str:
    name, kwargs = job
    assert name == "send_email"
    link = next(w for w in kwargs["text"].split() if w.startswith("http"))
    token: str = parse_qs(urlparse(link).query)["token"][0]
    return token


async def invite_and_join(
    client: AsyncClient,
    idp: FakeIdP,
    owner: Browser,
    business_id: str,
    sent_jobs: list[tuple[str, dict[str, Any]]],
    user: FakeUser,
    role: str,
    *,
    mfa: bool = False,
) -> Browser:
    created = await owner.post(
        f"/api/v1/businesses/{business_id}/invitations", json={"email": user.email, "role": role}
    )
    assert created.status_code == 201, created.text
    token = token_from(sent_jobs[-1])
    invitee = await browser_login(client, idp, user, mfa=mfa)
    accepted = await invitee.post("/api/v1/invitations/accept", json={"token": token})
    assert accepted.status_code == 200, accepted.text
    return invitee


async def test_invitation_email_is_sent_in_hebrew_after_commit(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)

        response = await owner.post(
            f"/api/v1/businesses/{business_id}/invitations",
            json={"email": "dana@example.com", "role": "member"},
        )

        assert response.status_code == 201
        assert len(sent_jobs) == 1
        _, email = sent_jobs[0]
        assert email["to"] == "dana@example.com"
        assert email["subject"] == "הזמנה להצטרף לדוגמה בע״מ"
        assert 'dir="rtl"' in email["html"]
        pending = (await owner.get(f"/api/v1/businesses/{business_id}/invitations")).json()
        assert [i["email"] for i in pending] == ["dana@example.com"]


async def test_invitee_previews_and_accepts(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        await owner.post(
            f"/api/v1/businesses/{business_id}/invitations",
            json={"email": "dana@example.com", "role": "accountant"},
        )
        token = token_from(sent_jobs[0])
        dana = await browser_login(client, idp, FakeUser(email="dana@example.com"))

        preview = await dana.get("/api/v1/invitations/preview", params={"token": token})
        accepted = await dana.post("/api/v1/invitations/accept", json={"token": token})
        again = await dana.post("/api/v1/invitations/accept", json={"token": token})

        assert preview.json() | {"expires_at": None} == {
            "business_name": "דוגמה בע״מ",
            "invited_by_name": "בעלת העסק",
            "email": "dana@example.com",
            "role": "accountant",
            "expires_at": None,
            "status": "pending",
        }
        assert accepted.json() == {"business_id": business_id}
        assert again.json()["error"]["code"] == "invitation_accepted"
        me = (await dana.get("/api/v1/me")).json()
        assert [(m["business"]["id"], m["role"]) for m in me["memberships"]] == [
            (business_id, "accountant")
        ]


async def test_invitation_only_works_for_the_invited_email(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        await owner.post(
            f"/api/v1/businesses/{business_id}/invitations",
            json={"email": "dana@example.com", "role": "member"},
        )
        token = token_from(sent_jobs[0])
        mallory = await browser_login(client, idp, FakeUser(email="mallory@example.com"))

        response = await mallory.post("/api/v1/invitations/accept", json={"token": token})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invitation_email_mismatch"


async def test_revoked_invitation_cannot_be_accepted(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        created = await owner.post(
            f"/api/v1/businesses/{business_id}/invitations",
            json={"email": "dana@example.com", "role": "member"},
        )
        token = token_from(sent_jobs[0])
        await owner.delete(f"/api/v1/businesses/{business_id}/invitations/{created.json()['id']}")
        dana = await browser_login(client, idp, FakeUser(email="dana@example.com"))

        response = await dana.post("/api/v1/invitations/accept", json={"token": token})

        assert response.json()["error"]["code"] == "invitation_revoked"


async def test_admin_must_use_two_factor(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        admin = await invite_and_join(
            client, idp, owner, business_id, sent_jobs, FakeUser(email="admin@example.com"), "admin"
        )

        response = await admin.get(f"/api/v1/businesses/{business_id}")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "mfa_required"


@pytest.mark.parametrize(
    ("role", "can_view_members", "can_invite", "can_view_audit"),
    [
        ("viewer", False, False, False),
        ("member", True, False, False),
        ("accountant", True, False, True),
    ],
)
async def test_role_permissions(
    idp: FakeIdP,
    sent_jobs: list[tuple[str, dict[str, Any]]],
    role: str,
    can_view_members: bool,
    can_invite: bool,
    can_view_audit: bool,
) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        user = await invite_and_join(
            client, idp, owner, business_id, sent_jobs, FakeUser(email="u@example.com"), role
        )
        base = f"/api/v1/businesses/{business_id}"

        assert (await user.get(base)).status_code == 200
        assert ((await user.get(f"{base}/members")).status_code == 200) is can_view_members
        assert ((await user.get(f"{base}/audit-log")).status_code == 200) is can_view_audit
        invite = await user.post(
            f"{base}/invitations", json={"email": "x@example.com", "role": "viewer"}
        )
        assert (invite.status_code == 201) is can_invite
        assert (await user.patch(base, json={"phone": "1"})).status_code == 403


async def test_owner_rules(idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]) -> None:
    async with app_client() as client:
        owner, business_id = await setup_business(client, idp)
        admin = await invite_and_join(
            client,
            idp,
            owner,
            business_id,
            sent_jobs,
            FakeUser(email="admin@example.com"),
            "admin",
            mfa=True,
        )
        base = f"/api/v1/businesses/{business_id}"
        members = {m["email"]: m for m in (await admin.get(f"{base}/members")).json()}
        owner_member = members["owner@example.com"]["id"]
        admin_member = members["admin@example.com"]["id"]

        # Admins cannot touch owners or create new ones.
        assert (
            await admin.patch(f"{base}/members/{owner_member}", json={"role": "viewer"})
        ).status_code == 403
        assert (
            await admin.patch(f"{base}/members/{admin_member}", json={"role": "owner"})
        ).status_code == 403
        assert (await admin.delete(f"{base}/members/{owner_member}")).status_code == 403
        invite_owner = await admin.post(
            f"{base}/invitations", json={"email": "z@example.com", "role": "owner"}
        )
        assert invite_owner.status_code == 403

        # The last owner can neither be demoted nor leave.
        owner = await browser_login(client, idp, OWNER, mfa=True)
        demote = await owner.patch(f"{base}/members/{owner_member}", json={"role": "admin"})
        leave = await owner.delete(f"{base}/members/{owner_member}")
        assert demote.json()["error"]["code"] == "last_owner"
        assert leave.json()["error"]["code"] == "last_owner"

        # Promote the admin, after which the original owner may step down.
        assert (
            await owner.patch(f"{base}/members/{admin_member}", json={"role": "owner"})
        ).status_code == 200
        assert (
            await owner.patch(f"{base}/members/{owner_member}", json={"role": "admin"})
        ).status_code == 200
        actions = [e["action"] for e in (await owner.get(f"{base}/audit-log")).json()]
        assert actions.count("member.role_changed") == 2
