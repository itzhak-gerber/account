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
| MCP endpoint | http://localhost:5173/mcp/ (OAuth bearer token from Keycloak) |
| Keycloak (login server) admin | http://localhost:8080 (admin / admin) |
| Mailpit (catches all emails sent locally) | http://localhost:8025 |

### Development users

The local Keycloak realm (`infra/keycloak/realm-invoice.dev.json`, **development only**) comes
with two users, password `Dev-Password-123`:

| Email | Notes |
|---|---|
| `owner@example.com` | Use to create a business. You will be asked to set up two-factor authentication (any authenticator app works, e.g. Google Authenticator). |
| `member@example.com` | Use to accept an invitation. Invitation emails appear in Mailpit. |

You can also register new users from the login page; the verification email arrives in Mailpit.

### What you can do today

1. Sign in as `owner@example.com`, set up two-factor, and create a business (fill in the
   address: tax documents need it).
2. **פריטים** (Items) and **לקוחות** (Customers): add your catalog and customers.
3. **מסמך חדש** (New document): quote, proforma, tax invoice, receipt, tax invoice-receipt.
   Pick a customer and items, see VAT and totals live, save a draft, preview the PDF, then
   **הפקת המסמך** (issue). Issued documents get the next number and can no longer change.
4. From an issued quote: convert to an invoice. From an invoice: **הפקת זיכוי** (credit note).
5. **הורדת PDF**: the first download is the original (מקור), later ones are marked as copies.
6. **Settings → פרטי העסק**: upload the business logo; it prints on new documents.
7. **Receipts pay invoices**: in a receipt, pick open invoices (the amount fills in with the open
   balance and can be changed), or press **הפקת קבלה** on an unpaid invoice. Invoices then show
   paid / partly paid, and the documents list has a **לא שולמו** (unpaid) filter.
8. **שליחה במייל** on an issued document: emails it to the customer with the PDF attached.
   The document page shows each send and whether it went out. In development every email
   lands in Mailpit at http://localhost:8025 instead of a real inbox.
9. **לוח בקרה** (Dashboard): this month's income, VAT and money received, what customers owe
   (and how much is late), and a 12-month chart.
10. **דוחות** (Reports): income and VAT for any period (presets include the last two-month VAT
    period), money received by payment method, and open balances by customer with days late.
    Each report downloads to Excel (**הורדה לאקסל**).
11. **התראות** (Notifications, the bell at the top): payments received, documents issued by
    others or by an AI assistant, invoices not paid on time (checked daily), failed emails to
    customers, and new team members. Choose what also comes by email under
    **פרופיל ואבטחה** (Profile). Phone push notifications come once the app runs on HTTPS.
12. **Daily summary** by email every morning (07:30): what was issued and received yesterday,
    and what customers owe. **New-device alerts**: signing in from a browser the account has not
    used before sends an alert; the profile page lists your devices and lets you remove one.

### Running in Azure

The test environment in Azure ("dev") is described in [infra/azure/README.md](infra/azure/README.md):
a one-time setup script for Cloud Shell, then every push deploys automatically after the tests pass.

### Connecting an AI assistant (MCP)

The MCP endpoint is protected with OAuth 2.1. Clients discover the login server from
`/.well-known/oauth-protected-resource/mcp`. For local testing, the dev-only client
`invoice-dev-cli` can issue a token with a password grant:

```bash
curl -s http://localhost:8080/realms/invoice/protocol/openid-connect/token \
  -d grant_type=password -d client_id=invoice-dev-cli \
  -d username=member@example.com -d password=Dev-Password-123 | jq -r .access_token
```

Owners and admins must use two-factor authentication, so their tokens must come from a login
that included the one-time code.

### Use it from a phone on the same Wi-Fi

1. Find this computer's address on the network: on Windows run `ipconfig` and take the
   "IPv4 Address" of the Wi-Fi adapter (looks like `192.168.1.20`); on Mac, System Settings →
   Wi-Fi → Details.
2. In the `account` folder create a file named `.env` containing that address, e.g. in a
   Windows command prompt: `echo APP_HOST=192.168.1.20>.env`
3. Restart: `Ctrl+C`, then `docker compose up --build`.
4. Open **http://192.168.1.20:5173** (your address) on the phone **and** on the computer.
   Always use this address while `.env` is set; `localhost` sessions do not carry over.

If Windows asks whether to allow Docker on the network, allow it for private networks. If the
computer's address changes (routers sometimes reassign it), update `.env` and restart. To go
back to `localhost`, delete `.env` and restart. Away from home, use the Azure environment (M1b).

Stop with `Ctrl+C` (or `docker compose down`). Businesses, customers, documents, PDFs and
logins (including two-factor setup) are kept in Docker volumes and are there next time.
`docker compose down -v` deletes all of it and starts fresh.

## Develop without Docker

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and the infrastructure
services from Docker: `docker compose up postgres redis keycloak mailpit`.

```bash
# backend
cd backend
uv sync
# migrations run as the schema owner; the app itself connects as the restricted invoice_app role
APP_DATABASE_URL=postgresql+asyncpg://invoice:invoice@localhost:5432/invoice uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run arq app.jobs.worker.WorkerSettings   # background jobs (emails), in another terminal

# frontend (another terminal)
cd frontend
npm install
npm run dev
```

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app tests && uv run pytest   # needs postgres + redis
cd frontend && npm run lint && npm run typecheck && npm test
```

CI runs all of these plus Docker image builds on every push.

## Layout

```
backend/    FastAPI app: REST API (/api/v1), MCP server (/mcp), worker, migrations
frontend/   React + TypeScript + MUI, Hebrew RTL
infra/      Keycloak realm + Hebrew login theme, Postgres init
docs/       Plan and design documents
```

Security model in short:

- **Login**: Keycloak (OpenID Connect). The browser never sees tokens; the backend keeps them
  in Redis and gives the browser an httpOnly session cookie, with a CSRF token for writes.
- **Two-factor authentication** is required for business owners and admins (checked on every
  request, for the web app and MCP alike).
- **Tenant isolation**: every business-owned row has `business_id`, and PostgreSQL row-level
  security policies enforce it for the app's database role, even if a query forgets a filter.
- **Audit log**: every change is recorded with who, when, from where and via which channel; the
  table is append-only at the database level.

Business logic lives in `backend/app/services/`. REST routers (`app/api/`) and MCP tools
(`app/mcp/`) are thin adapters over it, so every feature is available to both.
