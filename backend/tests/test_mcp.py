from typing import Any

from httpx import AsyncClient
from mcp import Client

from app.mcp.server import build_mcp_server
from tests.fake_idp import FakeIdP, FakeUser
from tests.helpers import VALID_BUSINESS, app_client, browser_login

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


async def call_tool(client: AsyncClient, token: str, name: str, arguments: dict[str, Any]) -> Any:
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {token}"}
    init = await client.post("/mcp/", json=INIT, headers=headers)
    assert init.status_code == 200, init.text
    response = await client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers={**headers, "MCP-Protocol-Version": "2025-06-18"},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


async def test_tools_are_registered() -> None:
    async with Client(build_mcp_server(with_auth=False)) as client:
        tools = {t.name for t in (await client.list_tools()).tools}

        assert {
            "get_system_status",
            "whoami",
            "list_businesses",
            "get_business",
            "list_members",
        } <= tools


async def test_mcp_requires_bearer_token_and_points_to_metadata() -> None:
    async with app_client() as client:
        response = await client.post("/mcp/", json=INIT, headers=MCP_HEADERS)

        assert response.status_code == 401
        assert "/.well-known/oauth-protected-resource/mcp" in response.headers["www-authenticate"]


async def test_protected_resource_metadata_names_keycloak() -> None:
    async with app_client() as client:
        response = await client.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 200
        assert response.json()["resource"] == "http://localhost/mcp"
        assert response.json()["authorization_servers"] == ["http://idp.test/realms/invoice"]


async def test_mcp_rejects_unknown_host(idp: FakeIdP) -> None:
    token = idp.access_token(FakeUser(email="a@example.com"))
    async with app_client() as client:
        response = await client.post(
            "/mcp/",
            json=INIT,
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}", "Host": "evil.example.com"},
        )

        assert response.status_code in (400, 403, 421)


async def test_mcp_tools_use_the_same_permissions_as_the_api(idp: FakeIdP) -> None:
    owner = FakeUser(email="owner@example.com")
    async with app_client() as client:
        browser = await browser_login(client, idp, owner, mfa=True)
        business_id = (await browser.post("/api/v1/businesses", json=VALID_BUSINESS)).json()[
            "business"
        ]["id"]

        with_mfa = idp.access_token(owner, mfa=True)
        without_mfa = idp.access_token(owner, mfa=False)
        stranger = idp.access_token(FakeUser(email="x@example.com"), mfa=True)

        listed = await call_tool(client, with_mfa, "list_businesses", {})
        details = await call_tool(client, with_mfa, "get_business", {"business_id": business_id})
        no_mfa = await call_tool(client, without_mfa, "get_business", {"business_id": business_id})
        foreign = await call_tool(client, stranger, "get_business", {"business_id": business_id})

        assert [b["role"] for b in listed["structuredContent"]["result"]] == ["owner"]
        assert details["structuredContent"]["tax_id"] == "516179157"
        assert no_mfa["isError"] is True
        assert "Two-factor" in no_mfa["content"][0]["text"]
        assert foreign["isError"] is True
        assert "not found" in foreign["content"][0]["text"].lower()
