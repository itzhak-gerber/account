# Invoice Platform (חשבוניות)

Multi-tenant web platform for Israeli businesses to issue quotes, invoices, receipts and
credit notes. Hebrew right-to-left UI for desktop and mobile browsers, FastAPI backend,
PostgreSQL, and a built-in MCP server so AI assistants can work with the same data.

See [docs/PLAN.md](docs/PLAN.md) for the full design and roadmap.

## Run it locally (Docker)

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/itzhak-gerber/account
cd account
docker compose up --build
```

| What | URL |
|---|---|
| App | http://localhost:5173 |
| API docs | http://localhost:8000/api/docs |
| MCP endpoint | http://localhost:8000/mcp/ |
| Keycloak admin | http://localhost:8080 (admin / admin) |

To open the app from your phone, connect it to the same Wi-Fi and browse to
`http://<your-computer's-IP>:5173`.

Stop with `Ctrl+C`; `docker compose down -v` also deletes the local database.

## Develop without Docker

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and a running
PostgreSQL 16 and Redis (e.g. `docker compose up postgres redis keycloak`).

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# frontend (another terminal)
cd frontend
npm install
npm run dev
```

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app tests && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm test
```

CI runs all of these plus Docker image builds on every push.

## Layout

```
backend/    FastAPI app: REST API (/api/v1), MCP server (/mcp), worker, migrations
frontend/   React + TypeScript + MUI, Hebrew RTL
docs/       Plan and design documents
```

Business logic lives in `backend/app/services/`. REST routers (`app/api/`) and MCP tools
(`app/mcp/`) are thin adapters over it, so every feature is available to both.
