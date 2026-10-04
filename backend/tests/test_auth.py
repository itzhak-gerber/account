from urllib.parse import parse_qs, urlparse

import pytest

from app.auth.principal import get_session_store
from app.core.config import get_settings
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import app_client, browser_login


async def test_unauthenticated_requests_get_401() -> None:
    async with app_client() as client:
        response = await client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"


async def test_login_redirects_to_idp_with_pkce_and_binds_state_cookie(idp: FakeIdP) -> None:
    async with app_client() as client:
        response = await client.get("/auth/login", params={"return_to": "//evil.example"})

        location = urlparse(response.headers["location"])
        params = parse_qs(location.query)
        assert location.path.endswith("/protocol/openid-connect/auth")
        assert params["code_challenge_method"] == ["S256"]
        assert params["ui_locales"] == ["he"]
        assert response.cookies["login_state"] == params["state"][0]


async def test_login_creates_user_and_session(idp: FakeIdP) -> None:
    user = FakeUser(email="dana@example.com", name="דנה כהן")
    async with app_client() as client:
        browser = await browser_login(client, idp, user)

        me = (await browser.get("/api/v1/me")).json()
        assert me["user"]["email"] == "dana@example.com"
        assert me["user"]["full_name"] == "דנה כהן"
        assert me["memberships"] == []
        assert me["mfa"] is False
        assert "session" in client.cookies
        # Tokens stay on the server: the only cookie value is an opaque session id.
        assert "." not in client.cookies["session"]


async def test_callback_rejects_state_from_another_browser(idp: FakeIdP) -> None:
    user = FakeUser(email="a@example.com")
    async with app_client() as client:
        start = await client.get("/auth/login")
        params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
        code = idp.issue_code(user, nonce=params["nonce"])
        client.cookies.clear()  # a different browser has no login_state cookie

        response = await client.get(
            "/auth/callback", params={"state": params["state"], "code": code}
        )

        assert response.status_code == 302
        assert "auth_error=login_state_mismatch" in response.headers["location"]
        assert (await client.get("/api/v1/me")).status_code == 401


async def test_unverified_email_cannot_sign_in(idp: FakeIdP) -> None:
    user = FakeUser(email="new@example.com", email_verified=False)
    async with app_client() as client:
        token = idp.access_token(user)
        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "email_not_verified"


async def test_writes_require_csrf_token(idp: FakeIdP) -> None:
    async with app_client() as client:
        await browser_login(client, idp, FakeUser(email="a@example.com"), mfa=True)

        response = await client.post("/api/v1/businesses", json={})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"


async def test_logout_ends_session_and_returns_idp_logout_url(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"))
        session_id = client.cookies["session"]

        response = await browser.post("/auth/logout")

        assert response.status_code == 200
        assert "/protocol/openid-connect/logout" in response.json()["logout_url"]
        client.cookies.set("session", session_id)  # replaying the old cookie must not work
        assert (await client.get("/api/v1/me")).status_code == 401


async def test_logout_all_ends_every_session(idp: FakeIdP) -> None:
    user = FakeUser(email="a@example.com")
    async with app_client() as client:
        first = await browser_login(client, idp, user)
        first_cookie = client.cookies["session"]
        second = await browser_login(client, idp, user)

        response = await second.post("/auth/logout-all")

        assert response.json()["sessions_ended"] == 2
        client.cookies.set("session", first_cookie)
        assert (await first.get("/api/v1/me")).status_code == 401


async def _expire_access_token(session_id: str) -> None:
    store = get_session_store()
    data = await store.get(session_id)
    assert data is not None
    data.access_expires_at = 0
    await store.save(session_id, data)


async def test_session_refreshes_with_idp_when_access_token_expires(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"))
        await _expire_access_token(client.cookies["session"])

        assert (await browser.get("/api/v1/me")).status_code == 200


async def test_session_ends_when_idp_refuses_refresh(idp: FakeIdP) -> None:
    async with app_client() as client:
        browser = await browser_login(client, idp, FakeUser(email="a@example.com"))
        await _expire_access_token(client.cookies["session"])
        idp.refresh_fails = True  # e.g. the user was disabled in Keycloak

        response = await browser.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_expired"


async def test_bearer_token_works_for_api(idp: FakeIdP) -> None:
    user = FakeUser(email="api@example.com")
    async with app_client() as client:
        token = idp.access_token(user)

        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "api@example.com"
        assert response.json()["csrf_token"] is None


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"iss": "http://evil.example/realms/x"}, {"exp": 1}],
    ids=["wrong-audience", "wrong-issuer", "expired"],
)
async def test_bearer_token_validation(idp: FakeIdP, overrides: dict[str, object]) -> None:
    user = FakeUser(email="api@example.com")
    async with app_client() as client:
        token = idp.access_token(user, **overrides)  # type: ignore[arg-type]

        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401


async def test_auth_endpoints_are_rate_limited(
    monkeypatch: pytest.MonkeyPatch, idp: FakeIdP
) -> None:
    monkeypatch.setenv("APP_RATE_LIMIT_AUTH_PER_MINUTE", "3")
    get_settings.cache_clear()
    async with app_client() as client:
        codes = [(await client.get("/auth/login")).status_code for _ in range(5)]

        assert codes[:3] == [302, 302, 302]
        assert codes[3:] == [429, 429]


async def test_after_setting_up_two_factor_user_signs_in_again(idp: FakeIdP) -> None:
    user = FakeUser(email="a@example.com")
    async with app_client() as client:
        start = await client.get(
            "/auth/login", params={"action": "CONFIGURE_TOTP", "return_to": "/settings"}
        )
        params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
        assert params["kc_action"] == "CONFIGURE_TOTP"
        code = idp.issue_code(user, nonce=params["nonce"], mfa=False)

        done = await client.get("/auth/callback", params={"state": params["state"], "code": code})

        assert done.status_code == 302
        assert done.headers["location"] == "/auth/login?return_to=%2Fsettings&reauth=true"
        assert (await client.get("/api/v1/me")).status_code == 401
