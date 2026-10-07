from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from httpx import ASGITransport, AsyncClient, Response

from app.main import create_app
from tests.fake_idp import FakeIdP, FakeUser


@asynccontextmanager
async def app_client() -> AsyncIterator[AsyncClient]:
    """Run the app (including its lifespan) and yield an HTTP client for it.

    A context manager rather than a fixture: the MCP session manager uses an anyio task
    group, which must be entered and exited in the same task.
    """
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client,
    ):
        yield client


@asynccontextmanager
async def second_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Another browser (own cookies) on the same running app, for tests with several users."""
    async with AsyncClient(transport=client._transport, base_url=client.base_url) as other:
        yield other


@dataclass
class Browser:
    """A logged-in browser: cookies live in the client, CSRF token is sent on writes."""

    client: AsyncClient
    csrf: str

    async def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        return await self.client.get(url, params=params)

    async def post(self, url: str, json: object = None) -> Response:
        return await self.client.post(url, json=json, headers={"X-CSRF-Token": self.csrf})

    async def patch(self, url: str, json: object = None) -> Response:
        return await self.client.patch(url, json=json, headers={"X-CSRF-Token": self.csrf})

    async def put(self, url: str, json: object = None) -> Response:
        return await self.client.put(url, json=json, headers={"X-CSRF-Token": self.csrf})

    async def delete(self, url: str) -> Response:
        return await self.client.delete(url, headers={"X-CSRF-Token": self.csrf})


async def browser_login(
    client: AsyncClient, idp: FakeIdP, user: FakeUser, *, mfa: bool = False
) -> Browser:
    client.cookies.clear()
    start = await client.get("/auth/login", params={"return_to": "/settings"})
    assert start.status_code == 302, start.text
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
    code = idp.issue_code(user, nonce=params["nonce"], mfa=mfa)
    done = await client.get("/auth/callback", params={"state": params["state"], "code": code})
    assert done.status_code == 302, done.text
    assert done.headers["location"] == "/settings"
    me = await client.get("/api/v1/me")
    assert me.status_code == 200, me.text
    return Browser(client=client, csrf=me.json()["csrf_token"])


VALID_BUSINESS = {
    "legal_name": "דוגמה בע״מ",
    "tax_id": "516179157",
    "business_type": "company",
    "address_city": "תל אביב",
}
