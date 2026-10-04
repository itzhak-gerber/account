from mcp import Client

from app.mcp.server import build_mcp_server
from tests.helpers import app_client

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


async def test_mcp_lists_and_calls_system_status_tool() -> None:
    async with Client(build_mcp_server()) as client:
        tools = await client.list_tools()
        assert "get_system_status" in {t.name for t in tools.tools}

        result = await client.call_tool("get_system_status", {})
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["database"] == "ok"


async def test_mcp_is_mounted_over_http() -> None:
    async with app_client() as client:
        response = await client.post("/mcp/", json=INIT, headers=MCP_HEADERS)

        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "invoice-platform"


async def test_mcp_rejects_unknown_host() -> None:
    async with app_client() as client:
        response = await client.post(
            "/mcp/", json=INIT, headers={**MCP_HEADERS, "Host": "evil.example.com"}
        )

        assert response.status_code in (400, 403, 421)
