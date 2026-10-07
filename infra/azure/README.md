# Azure "dev" environment

Everything runs in one resource group in **Israel Central**:

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

## One-time setup

1. In the Azure portal open **Cloud Shell** (`>_` at the top), choose **Bash**.
2. Upload `infra/azure/bootstrap.sh` (Cloud Shell toolbar: *Manage files* → *Upload*).
3. Run `bash bootstrap.sh`. At the end it prints a value named `AZURE_ENV`.
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

## Useful commands (Cloud Shell)

```bash
az containerapp logs show -g rg-invoice-dev -n backend --follow     # live backend logs
az containerapp job execution list -g rg-invoice-dev -n migrate -o table
az keyvault secret show --vault-name <vault> -n keycloak-admin-password --query value -o tsv
```

The Keycloak admin console is at `https://auth.<env>.../admin` (user `admin`, password in
Key Vault as `keycloak-admin-password`).
