import io
from typing import Any

from PIL import Image

from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import Browser, app_client
from tests.test_documents import draft, issue, setup
from tests.test_members import invite_and_join


def png(width: int = 1600, height: int = 400) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (30, 79, 216)).save(out, format="PNG")
    return out.getvalue()


async def upload(browser: Browser, bid: str, content: bytes, name: str = "logo.png") -> Any:
    return await browser.client.put(
        f"/api/v1/businesses/{bid}/logo",
        files={"file": (name, content, "image/png")},
        headers={"X-CSRF-Token": browser.csrf},
    )


async def test_owner_uploads_logo_and_it_is_resized(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)

        response = await upload(owner, bid, png())
        stored = await owner.get(f"/api/v1/businesses/{bid}/logo")

        assert response.status_code == 200, response.text
        assert response.json()["has_logo"] is True
        assert stored.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(stored.content)).size == (800, 200)


async def test_logo_upload_rejects_non_images(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)

        fake = await upload(owner, bid, b"<svg onload=alert(1)>", name="logo.svg")
        huge = await upload(owner, bid, b"0" * (3 * 1024 * 1024))

        assert fake.json()["error"]["code"] == "invalid_image"
        assert huge.json()["error"]["code"] == "image_too_large"


async def test_only_owner_and_admin_change_the_logo(
    idp: FakeIdP, sent_jobs: list[tuple[str, dict[str, Any]]]
) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        member = await invite_and_join(
            client, idp, owner, bid, sent_jobs, FakeUser(email="m@example.com"), "member"
        )

        assert (await upload(member, bid, png())).status_code == 403


async def test_logo_appears_in_pdfs_and_issued_documents_keep_theirs(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        await upload(owner, bid, png())
        doc = await draft(owner, bid)
        await issue(owner, bid, doc["id"])
        url = f"/api/v1/businesses/{bid}/documents/{doc['id']}/pdf"

        original = await owner.get(url)
        removed = await owner.client.delete(
            f"/api/v1/businesses/{bid}/logo", headers={"X-CSRF-Token": owner.csrf}
        )
        copy = await owner.get(url)
        later = await draft(owner, bid)
        later_preview = await owner.get(f"/api/v1/businesses/{bid}/documents/{later['id']}/pdf")

        assert b"/Subtype /Image" in original.content
        assert removed.status_code == 204
        assert copy.headers["X-Document-Variant"] == "copy"
        assert b"/Subtype /Image" in copy.content  # issued with the logo
        assert b"/Subtype /Image" not in later_preview.content
