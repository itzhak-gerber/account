"""MCP server. Tools are thin adapters over the service layer, exactly like REST routers."""

from mcp.server.mcpserver import MCPServer

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services.system import SystemStatus, get_system_status


def build_mcp_server() -> MCPServer:
    mcp = MCPServer(
        name="invoice-platform",
        version=get_settings().version,
        instructions=(
            "Invoice platform for Israeli businesses: customers, items, quotes, invoices, "
            "receipts and credit notes. Documents are created as drafts; issuing is irreversible."
        ),
    )

    @mcp.tool(name="get_system_status")
    async def get_system_status_tool() -> SystemStatus:
        """Return the platform status (version, environment, database health)."""
        async with get_sessionmaker()() as session:
            return await get_system_status(session)

    return mcp
