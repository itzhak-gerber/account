# Invoice Platform: Project Plan

A multi-tenant, production-grade web platform for Israeli businesses to create
invoices, receipts, and related documents. It has a Hebrew (RTL) responsive UI,
a FastAPI backend, PostgreSQL, and a built-in MCP server so AI agents can work
with the same data under the same security rules.

> Status: **draft for review**. Open decisions are listed in [§12](#12-open-decisions).

---

## 1. Goals and non-goals

**Goals**
- Businesses can register, invite team members, and issue legally valid Israeli
  documents: quote, proforma invoice, tax invoice, receipt, tax invoice-receipt,
  and credit note.
- One responsive web app for desktop and mobile browsers, in Hebrew and RTL.
- Production-ready from day one: strong authentication, tenant isolation, audit
  trail, backups, observability.
- **MCP-first**: every business capability is available to AI clients through
  MCP, with the same permissions as the REST API.
- Cloud-portable: runs on AWS or Azure without code changes.

**Non-goals for v1**
- Native mobile apps.
- Full bookkeeping/ledger (we produce documents and exports for accountants, not a general ledger).
- Payroll and inventory management.

---

## 2. Domain: Israeli invoicing requirements

These rules shape the data model. **Have an Israeli CPA confirm them before go-live.**

| Hebrew | English / code | Notes |
|---|---|---|
| הצעת מחיר | `quote` | Not a tax document. Can be converted to an invoice. |
| חשבונית עסקה | `proforma_invoice` | Demand for payment. Not a tax document. |
| חשבונית מס | `tax_invoice` | VAT document. Licensed dealers (עוסק מורשה) and companies only. |
| קבלה | `receipt` | Confirms payment. Lists payment methods. |
| חשבונית מס/קבלה | `tax_invoice_receipt` | Combined document for payment at the time of sale. |
| חשבונית זיכוי | `credit_note` | The only way to cancel or correct an issued tax invoice. |

**Rules the system must enforce**
1. **Gapless sequential numbering** per business and document type. Numbers are
   assigned only when a document is issued, never for drafts.
2. **Issued documents are immutable.** They can't be edited or deleted; corrections
   go through a credit note. This is enforced in the service layer *and* by a DB trigger.
3. **Original/copy:** the first rendering is marked "מקור" and later ones "העתק".
4. **VAT rate by date:** a `vat_rates` table with effective dates (currently 18%,
   since 2025-01-01). Never hard-code the rate.
5. **Business type:** an exempt dealer (עוסק פטור) can't issue tax invoices,
   only receipts and proforma invoices.
6. **Allocation number (מספר הקצאה, "חשבוניות ישראל" reform):** B2B tax invoices
   above a threshold need an allocation number from the Israel Tax Authority (ITA) API.
   The threshold drops over time, so store it as configuration with effective dates.
7. **Software registration and exports:** software that produces invoices must be
   registered with the ITA and support the unified file format export
   (מבנה אחיד, OPENFRMT).
8. **Retention:** keep documents for at least 7 years. There is no hard delete of
   issued documents or businesses that have issued documents.
9. **Data residency:** prefer Israeli cloud regions (AWS `il-central-1`, Azure
   *Israel Central*). Comply with the Privacy Protection Regulations (Data
   Security) and Amendment 13.

---

## 3. Architecture

```
                 ┌──────────────── Browser (desktop / mobile) ────────────────┐
                 │  React + TypeScript SPA, Hebrew, RTL, responsive           │
                 └───────────────┬────────────────────────────────────────────┘
                                 │ HTTPS, httpOnly session cookie (BFF)
   AI clients (Claude, etc.)     │
   ── MCP over Streamable HTTP ──┤ Bearer access token (OAuth 2.1)
                                 ▼
 ┌──────────────────────────── FastAPI application ───────────────────────────┐
 │  /api/v1/*  REST routers  │  /mcp  MCP server  │  /auth/*  BFF login flow  │
 │──────────────────────────────────────────────────────────────────────────── │
 │   Principal resolution (cookie session OR bearer JWT) → tenant + roles     │
 │──────────────────────────────────────────────────────────────────────────── │
 │   SERVICE LAYER (single source of business logic, used by REST and MCP)    │
 │   customers · items · documents · numbering · vat · payments · reports     │
 │──────────────────────────────────────────────────────────────────────────── │
 │   Repositories (SQLAlchemy 2 async)  │  Integrations: storage, email, ITA  │
 └───────┬──────────────────────┬──────────────────────┬──────────────────────┘
         ▼                      ▼                      ▼
   PostgreSQL (RLS)        Redis (sessions,       Object storage (PDFs)
                           rate limits, jobs)     S3 / Azure Blob
         ▲
   Worker process (arq): PDF rendering, email sending, ITA allocation calls
   Identity provider (Keycloak, OIDC): users, passwords, MFA, OAuth for MCP
```

### Key design principles
- **Thin adapters, one service layer.** REST routers and MCP tools only parse
  input and call services. A feature isn't done until it has a service method, a
  REST endpoint, and an MCP tool, all with tests. This is what "MCP from the
  beginning" means in practice.
- **Tenant isolation in depth.** Every tenant-owned table has `business_id`.
  The app sets `app.business_id` per transaction, and **PostgreSQL Row-Level
  Security** policies enforce isolation even if a query forgets a filter.
- **Cloud abstraction at the edges only.** `StorageBackend`, `EmailSender`, and
  `SecretsProvider` interfaces have AWS and Azure implementations. Everything
  else is plain containers plus Postgres.
- **Money is `Decimal`/`NUMERIC(14,2)`**, never float. Rounding happens per line and
  then on the totals, following one documented rule.

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2 | Requested; typed; OpenAPI out of the box |
| ORM / migrations | SQLAlchemy 2.0 (async) + asyncpg, Alembic | Mature, async, explicit migrations |
| MCP | Official `mcp` Python SDK (FastMCP), Streamable HTTP transport, mounted at `/mcp` | Same process and services as REST |
| Jobs | arq + Redis | Async-native, light |
| PDF | WeasyPrint + Jinja2 HTML templates | Correct Hebrew bidi/RTL shaping, embedded fonts |
| Identity | **Keycloak** (OIDC/OAuth 2.1) | Runs on both clouds; MFA, brute-force protection, Hebrew login theme, dynamic client registration for MCP |
| Frontend | React 18 + TypeScript + Vite | Requested |
| UI kit | MUI with RTL (`stylis-plugin-rtl`), Hebrew locale, font *Heebo*/*Assistant* | Mature RTL support, responsive grid, date pickers |
| Data fetching | TanStack Query + API client generated from OpenAPI (`orval`) | Typed end to end |
| Forms | react-hook-form + zod | Line-item forms with validation |
| i18n | react-i18next (Hebrew only at first, all strings externalized) | Easy to add English later |
| DB | PostgreSQL 16 | Requested |
| Tests | pytest + testcontainers (real Postgres), Vitest, Playwright (desktop + mobile viewports) | |
| Quality | ruff, mypy (strict), eslint, prettier, pre-commit | |
| CI/CD | GitHub Actions → container registry → deploy | |
| IaC | Terraform (`infra/aws`, `infra/azure`) | |
| Observability | OpenTelemetry traces/metrics, structured JSON logs, Sentry | |

---

## 5. Data model (English names)

All tables have `id UUID PK`, `created_at`, and `updated_at`. Tenant-owned tables
have `business_id` with RLS.

**Identity and tenancy**
- `users`: `idp_subject` (Keycloak `sub`), `email`, `full_name`, `locale`, `is_active`
- `businesses`: `legal_name`, `display_name`, `tax_id` (ח.פ / ע.מ), `business_type`
  (`exempt_dealer` | `licensed_dealer` | `company` | `nonprofit`), `address`, `phone`,
  `email`, `logo_file_id`, `default_currency`, `settings JSONB`
- `business_members`: `business_id`, `user_id`, `role` (`owner` | `admin` |
  `accountant` | `member` | `viewer`), `status`
- `invitations`: `business_id`, `email`, `role`, `token_hash`, `expires_at`

**Catalog**
- `customers`: `name`, `tax_id`, `email`, `phone`, `address`, `notes`, `is_archived`
- `items`: `name`, `description`, `unit_price`, `vat_type` (`standard` | `exempt` | `zero`), `is_archived`

**Documents**
- `documents`: `type`, `status` (`draft` | `issued` | `cancelled`), `number` (null
  until issued), `issue_date`, `due_date`, `customer_id`, plus a **customer snapshot
  JSONB** and a **business snapshot JSONB** (frozen at issue), `currency`,
  `exchange_rate`, `subtotal`, `discount_total`, `vat_rate`, `vat_amount`, `total`,
  `amount_paid`, `payment_status` (`unpaid` | `partial` | `paid`), `notes`,
  `allocation_number`, `pdf_file_id`, `issued_by`, `issued_at`, `source` (`web` | `mcp` | `api`)
- `document_lines`: `document_id`, `position`, `item_id?`, `description`, `quantity`,
  `unit_price`, `discount`, `vat_type`, `line_total`
- `document_payments`: `document_id`, `method` (`cash` | `check` | `credit_card` |
  `bank_transfer` | `digital_wallet` | `other`), `amount`, `date`, method-specific
  fields (bank, branch, account, check number, card last 4, installments)
- `document_relations`: `from_document_id`, `to_document_id`, `relation`
  (`converted_from` | `credits` | `pays`)
- `document_sequences`: `business_id`, `document_type`, `next_number`. Locked with
  `SELECT … FOR UPDATE` inside the issue transaction, which makes numbering gapless.
- `vat_rates`: `rate`, `effective_from`
- `tax_allocation_requests`: `document_id`, `status`, `request`, `response`, `allocation_number`, `attempts`

**Platform**
- `files`: `storage_key`, `content_type`, `size`, `sha256`
- `email_deliveries`: `document_id`, `to`, `status`, `provider_message_id`
- `audit_logs` (append-only): `business_id`, `actor_user_id`, `actor_channel`
  (`web` | `mcp` | `api` | `system`), `action`, `entity`, `entity_id`, `diff JSONB`, `ip`, `user_agent`

---

## 6. Security and authentication

**Identity provider: Keycloak (OIDC).** We don't store passwords ourselves.
- Email verification, password policy, brute-force lockout, and **MFA (TOTP) required for owners/admins**
- Optional "Sign in with Google/Microsoft"
- Hebrew-themed login pages

**Web app uses the BFF pattern (Backend-for-Frontend).**
- FastAPI runs Authorization Code + PKCE with Keycloak. Tokens stay **server-side**
  in Redis, and the browser only gets an `httpOnly; Secure; SameSite=Lax` session
  cookie. No tokens in `localStorage`.
- CSRF protection uses a double-submit token on state-changing requests.
- Sessions time out after inactivity and have an absolute lifetime. Users can
  sign out of all sessions.

**MCP and API clients use OAuth 2.1 bearer tokens.**
- `/mcp` is an OAuth *resource server*. It publishes Protected Resource Metadata
  (`/.well-known/oauth-protected-resource`) that points to Keycloak, as the MCP
  authorization spec requires.
- Tokens are validated against Keycloak JWKS (issuer, **audience = this API**,
  expiry, scopes).
- Scopes: `customers:read`, `customers:write`, `documents:read`,
  `documents:write`, `documents:issue`, `reports:read`.

**Authorization**
- Both channels resolve to the same `Principal(user, business, role, scopes)`.
  Role and scope checks live in the service layer.
- RLS in Postgres is the second line of defense.

**Application hardening (target: OWASP ASVS Level 2)**
- TLS everywhere, HSTS, strict CSP, strict CORS (own origin only), secure headers
- Rate limiting per IP and per user (Redis); stricter on auth and issue endpoints
- Pydantic validation on all input; upload type and size limits; PDF links are short-lived signed URLs
- Least-privilege DB roles (the app role can't bypass RLS or alter the audit log)
- Secrets in AWS Secrets Manager / Azure Key Vault; encryption at rest; PITR backups
- Dependency and container scanning (Dependabot, `pip-audit`, `npm audit`, Trivy),
  SAST (Bandit, CodeQL), secret scanning
- Penetration test before public launch

---

## 7. MCP design

Mounted in the same FastAPI app at `/mcp` (Streamable HTTP). Tools call the same
service layer as REST.

| Tool | Scope | Notes |
|---|---|---|
| `list_businesses` | — | Businesses the user belongs to |
| `search_customers`, `get_customer` | `customers:read` | |
| `create_customer`, `update_customer` | `customers:write` | |
| `search_items` | `customers:read` | Catalog |
| `create_document_draft` | `documents:write` | Any type, creates a **draft** only |
| `update_document_draft` | `documents:write` | |
| `preview_document` | `documents:read` | Totals, VAT, and validation errors before issuing |
| `issue_document` | `documents:issue` | **Irreversible**: requires the explicit `draft_id` and returns the assigned number |
| `create_credit_note` | `documents:issue` | Against an issued invoice |
| `record_payment` / `create_receipt` | `documents:issue` | |
| `search_documents`, `get_document` | `documents:read` | Filter by type, status, customer, dates, payment status |
| `get_document_pdf_link` | `documents:read` | Short-lived signed URL |
| `send_document_email` | `documents:write` | |
| `get_report` | `reports:read` | Revenue, VAT, open balances, per period |

**Resources:** `business://{id}/profile`, `document://{id}`, `customer://{id}`.
**Prompts:** "create invoice from description" and "monthly summary".

Safety: tools never issue documents implicitly. Every MCP action is audited with
`actor_channel = 'mcp'`. MCP tokens can be revoked per client in Keycloak.

---

## 8. Frontend (Hebrew, RTL, responsive)

- `<html dir="rtl" lang="he">`; the MUI theme has `direction: 'rtl'`; CSS uses only
  logical properties; numbers, amounts, and tax IDs are wrapped with `dir="ltr"` where needed.
- Layout: side navigation on desktop, bottom navigation and drawer on mobile. The
  line-items editor turns into cards on small screens.
- Formatting: `Intl.NumberFormat('he-IL', {style:'currency', currency:'ILS'})`, dates `dd/MM/yyyy`.
- Main screens: dashboard · documents list · new document (type picker → customer
  → lines → payments → preview → issue) · document view (PDF, send, credit,
  receive payment) · customers · items · reports · business settings (details, logo,
  numbering start, users and roles, MCP/API connections) · profile and security.
- Accessibility: WCAG 2.1 AA, which is also required by Israeli accessibility regulations.

---

## 9. Repository layout

```
account/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/            # config, db session, logging, security headers, errors
│   │   ├── auth/            # BFF flow, JWT validation, Principal, permissions
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic DTOs
│   │   ├── services/        # ← business logic (shared by api + mcp)
│   │   ├── api/v1/          # REST routers (thin)
│   │   ├── mcp/             # MCP server, tools, resources (thin)
│   │   ├── integrations/    # storage/, email/, tax_authority/
│   │   ├── pdf/             # Jinja2 templates + fonts
│   │   └── jobs/            # arq worker tasks
│   ├── migrations/          # Alembic
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/{app,pages,components,features,api,i18n,theme}/
│   └── package.json
├── infra/
│   ├── keycloak/            # realm export, Hebrew theme
│   ├── terraform/aws/
│   └── terraform/azure/
├── docker-compose.yml       # postgres, redis, keycloak, backend, worker, frontend
├── .github/workflows/
└── docs/
```

---

## 10. Deployment

| Component | AWS | Azure |
|---|---|---|
| Containers (api, worker) | ECS Fargate | Azure Container Apps |
| Frontend | S3 + CloudFront | Static Web Apps / Blob + Front Door |
| PostgreSQL | RDS for PostgreSQL (Multi-AZ, PITR) | Azure Database for PostgreSQL Flexible Server (zone-redundant HA) |
| Redis | ElastiCache | Azure Cache for Redis |
| Object storage | S3 (versioned, Object Lock for issued PDFs) | Blob Storage (immutability policy) |
| Email | SES | Azure Communication Services Email |
| Secrets | Secrets Manager | Key Vault |
| WAF / edge | CloudFront + AWS WAF | Front Door + WAF |
| Keycloak | ECS + its own RDS DB | Container Apps + its own Postgres DB |

Environments: `local` (docker-compose) → `staging` → `production`. Migrations run
as a separate step before rollout. Deployments are blue/green or rolling.

---

## 11. Milestones

Each feature milestone includes REST, MCP tools, UI, tests, and audit logging.

| # | Milestone | Deliverables |
|---|---|---|
| **M0** | Foundations | Monorepo skeleton, docker-compose (Postgres, Redis, Keycloak), FastAPI + React "hello", CI (lint, types, tests), pre-commit, Alembic baseline, empty MCP server mounted at `/mcp` |
| **M1** | Auth and tenancy | Keycloak realm, BFF login/logout, JWT validation for MCP, Principal, businesses, members, invitations, roles, RLS policies, audit log, Hebrew RTL app shell |
| **M2** | Catalog | Customers and items: CRUD, search, UI, MCP tools |
| **M3** | Documents core | Drafts, line items, VAT calculation, gapless numbering, issue flow, immutability trigger, quote → invoice conversion, credit notes, Hebrew PDF (original/copy) |
| **M4** | Payments and delivery | Receipts and invoice-receipts, payment methods, payment status, email sending, signed PDF links |
| **M5** | Israeli compliance | ITA allocation-number integration (sandbox → production), OPENFRMT export, ITA software registration package |
| **M6** | Reports and dashboard | Revenue/VAT per period, open balances, CSV/Excel export, MCP `get_report` |
| **M7** | Production hardening | Terraform for the chosen cloud, observability, backups/restore drill, load test, security review and pen test, privacy policy and terms |
| **Later** | | Recurring invoices, online card payment links, multi-currency, accountant portal, digitally signed PDFs, English UI, subscription billing |

---

## 12. Open decisions

1. **First cloud: AWS or Azure?** The code is portable, but IaC and ops for v1 should
   target one. Both have Israeli regions.
2. **Identity provider:** self-hosted **Keycloak** (recommended: no per-user cost,
   cloud-neutral, MCP-friendly dynamic client registration) or managed **Auth0**
   (no IdP ops, paid per user).
3. **Product model:** a multi-tenant SaaS for many businesses (assumed here), or one
   business with many users?
4. **v1 document types:** all six, or start with tax invoice + receipt +
   invoice-receipt + credit note?
5. **ITA registration:** who will register the software with the Israel Tax
   Authority and get API credentials for allocation numbers?
