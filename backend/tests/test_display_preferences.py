"""Theme and text size are kept per user, so they follow the user to every device."""

from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import app_client, browser_login, second_client


async def test_display_preferences_follow_the_user(idp: FakeIdP) -> None:
    async with app_client() as client:
        dana = await browser_login(client, idp, FakeUser(email="dana@example.com"))
        user = (await dana.get("/api/v1/me")).json()["user"]
        assert (user["theme"], user["text_size"]) == ("system", "device")

        saved = await dana.patch("/api/v1/me/display-preferences", json={"theme": "dark"})
        assert saved.status_code == 200, saved.text
        assert (saved.json()["theme"], saved.json()["text_size"]) == ("dark", "device")
        saved = await dana.patch("/api/v1/me/display-preferences", json={"text_size": "xlarge"})
        assert (saved.json()["theme"], saved.json()["text_size"]) == ("dark", "xlarge")

        # Another device of the same user gets them too.
        async with second_client(client) as other:
            phone = await browser_login(other, idp, FakeUser(email="dana@example.com"))
            user = (await phone.get("/api/v1/me")).json()["user"]
            assert (user["theme"], user["text_size"]) == ("dark", "xlarge")

            # Someone else keeps the defaults.
            noa = await browser_login(other, idp, FakeUser(email="noa@example.com"))
            user = (await noa.get("/api/v1/me")).json()["user"]
            assert (user["theme"], user["text_size"]) == ("system", "device")


async def test_unknown_values_and_missing_csrf_are_refused(idp: FakeIdP) -> None:
    async with app_client() as client:
        dana = await browser_login(client, idp, FakeUser(email="dana@example.com"))
        bad = await dana.patch("/api/v1/me/display-preferences", json={"theme": "purple"})
        assert bad.status_code == 422
        bad = await dana.patch("/api/v1/me/display-preferences", json={"text_size": "huge"})
        assert bad.status_code == 422
        forged = await client.patch("/api/v1/me/display-preferences", json={"theme": "dark"})
        assert forged.status_code == 403
        assert (await dana.get("/api/v1/me")).json()["user"]["theme"] == "system"
