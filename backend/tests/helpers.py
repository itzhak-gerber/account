from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.main import create_app


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
