# Azure "dev" environment

One resource group, `rg-invoice-dev`, in **Sweden Central** (Container Apps is not offered in
Israel Central yet, and West Europe was not accepting new trial subscriptions). The network,
database and apps run in **North Europe** (Ireland), because Sweden Central refused every
database size to this subscription; registry, storage, Key Vault, identity and logs stay in
Sweden Central and are used from there:

| Part | Azure service | Notes |
|---|---|---|
| Web (`invoice.<env>.azurecontainerapps.io`) | Container App `invoice` (nginx) | Serves the app; forwards `/api`, `/auth`, `/mcp` to the backend |
| Backend API | Container App `backend` | Internal only |
| Background worker | Container App `worker` | Emails, notifications, daily jobs |
| Login (`auth.<env>...`) | Container App `auth` (Keycloak) | Production realm, Hebrew theme |
| Redis | Container App `redis` | Internal TCP only, password protected |
| Database | PostgreSQL Flexible Server (B1ms) | Private subnet, no public access, TLS |
| PDFs and logos | Blob Storage | Managed identity only (no keys), versioning, 30-day undelete |
| Secrets | Key Vault | Read by the apps' managed identity |
| Email | Azure Communication Services | Azure-managed sender domain, SMTP |
| Images | Container Registry (Basic) | |
| Logs | Log Analytics | 30 days |

## Current environment

| | |
|---|---|
| Subscription | Azure subscription 1 (`fb8aa579-e262-4701-834f-bb69d81db963`) |
| Region | Sweden Central (`swedencentral`); network, database and apps in North Europe (`northeurope`) |
| Resource group | `rg-invoice-dev` |
| Key Vault | `kv-invoice-dev-0d5e33` |
| GitHub variable | `AZURE_ENV` (identifiers only, set from `bootstrap.sh` output) |

## One-time setup

1. In the Azure portal open **Cloud Shell** (`>_` at the top), choose **Bash**.
2. Upload `infra/azure/bootstrap.sh` (Cloud Shell toolbar: *Manage files* → *Upload*).
3. Run `LOCATION=swedencentral bash bootstrap.sh`. At the end it prints a value named
   `AZURE_ENV`.
4. In GitHub: repository **Settings** → **Secrets and variables** → **Actions** →
   **Variables** → **New repository variable**: name `AZURE_ENV`, value as printed.

From then on every push to `main` or the working branch deploys automatically after the
tests pass (CI job **deploy**). The first deploy takes about 20–30 minutes (the database
server is the slowest part); later ones about 10.

## How a deploy works (`.github/workflows/deploy.yml`)

1. Signs in to Azure with OpenID Connect (no stored password).
2. Generates any missing secret into Key Vault (random, never printed).
3. `main.bicep` stage **base**: network, database, storage, registry, email.
4. Builds and pushes the backend, frontend and Keycloak images.
5. Stage **job**, then runs the **migrate** job: creates the restricted database role and
   Keycloak's database if needed, applies migrations.
6. Stage **apps**: rolls out the new version.
7. Smoke test: the app, the API health check and Keycloak.

## Pause and resume (saves most of the cost while not working)

On GitHub: **Actions** → **Pause dev environment** → **Run workflow**. All apps scale to zero
and the database stops; data is kept. **Resume dev environment** brings everything back in
about 5 minutes (any deploy resumes it too). Azure restarts a stopped database by itself after
7 days. Both also work from the GitHub mobile app.

## Database size, region and "no capacity"

New subscriptions are often refused small database servers in some regions, reported as
`RegionalAllocationFailed` ("no capacity"). In Sweden Central every size and zone was refused,
so the network, database and apps moved to North Europe. When it creates the server, the deploy
tries B1ms (any zone, then zone 1), then B2s, moving on only for that error. Later deploys keep
the existing server's size. Optional `AZURE_ENV` fields override the choices:

```json
"computeLocation": "germanywestcentral", "postgresSku": "Standard_B1ms", "postgresZone": "2"
```

Moving to another region creates new network/database/apps resources (their names include a
region-specific suffix); the old region's are left as they are and can be removed by hand.
A trial subscription allows only **one** Container Apps environment, so the old one must be
deleted first (`az containerapp env delete -g rg-invoice-dev -n <old environment> --yes`).

To scale an existing server down later (e.g. B2s to B1ms when capacity allows), use Cloud Shell:
`az postgres flexible-server update -g rg-invoice-dev -n <server> --sku-name Standard_B1ms`.

## Useful commands (Cloud Shell)

```bash
az containerapp logs show -g rg-invoice-dev -n backend --follow     # live backend logs
az containerapp job execution list -g rg-invoice-dev -n migrate -o table
az keyvault secret show --vault-name <vault> -n keycloak-admin-password --query value -o tsv
```

The Keycloak admin console is at `https://auth.<env>.../admin` (user `admin`, password in
Key Vault as `keycloak-admin-password`).
