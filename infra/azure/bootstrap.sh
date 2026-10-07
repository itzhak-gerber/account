#!/usr/bin/env bash
# One-time setup for the Azure "dev" environment. Run it in Azure Cloud Shell (Bash):
#
#     bash bootstrap.sh
#
# It is safe to run again: everything it creates is reused if it already exists.
#
# What it does (nothing here costs money by itself):
#   1. Registers the Azure services the platform uses, and checks they exist in the region.
#   2. Creates the resource group and a Key Vault for all secrets.
#   3. Lets GitHub Actions deploy without any stored password (OpenID Connect): an Entra app
#      that trusts only this repository's "dev" environment, with rights on this resource
#      group only.
#   4. Creates the Entra app used to send email (SMTP) and keeps its secret in the Key Vault.
#   5. Prints one GitHub variable (AZURE_ENV) to paste into the repository settings.
set -euo pipefail

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-fb8aa579-e262-4701-834f-bb69d81db963}"
LOCATION="${LOCATION:-israelcentral}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-invoice-dev}"
GITHUB_REPO="${GITHUB_REPO:-itzhak-gerber/account}"
GITHUB_ENVIRONMENT="dev"
DEPLOY_APP_NAME="invoice-github-deploy"
SMTP_APP_NAME="invoice-smtp"

step() { printf '\n==> %s\n' "$*"; }
retry() { # retry <attempts> <command...>: role assignments take a minute to take effect
  local n=$1; shift
  for ((i = 1; i <= n; i++)); do
    if "$@"; then return 0; fi
    echo "   (waiting for permissions to take effect, try $i/$n)"; sleep 15
  done
  return 1
}

step "Subscription"
az account set --subscription "$SUBSCRIPTION_ID"
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "   $(az account show --query name -o tsv) ($SUBSCRIPTION_ID), tenant $TENANT_ID"

step "Registering Azure services (first time can take a few minutes)"
NAMESPACES=(Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL
  Microsoft.KeyVault Microsoft.Storage Microsoft.OperationalInsights Microsoft.Communication
  Microsoft.ManagedIdentity Microsoft.Network)
for ns in "${NAMESPACES[@]}"; do az provider register --namespace "$ns" -o none; done
for ns in "${NAMESPACES[@]}"; do
  until [ "$(az provider show --namespace "$ns" --query registrationState -o tsv)" = "Registered" ]; do
    sleep 10
  done
  echo "   $ns registered"
done

step "Checking that every service is offered in $LOCATION"
normalise() { tr -d ' ' | tr '[:upper:]' '[:lower:]'; }
missing=0
for pair in Microsoft.App/managedEnvironments Microsoft.App/jobs \
  Microsoft.DBforPostgreSQL/flexibleServers Microsoft.ContainerRegistry/registries \
  Microsoft.KeyVault/vaults Microsoft.Storage/storageAccounts; do
  ns=${pair%%/*}; type=${pair#*/}
  # Read the whole list first: piping into "grep -q" can end the pipe early, which strict
  # mode (pipefail) would report as "not found".
  locations=$(az provider show --namespace "$ns" \
    --query "resourceTypes[?resourceType=='$type'].locations[]" -o tsv | normalise)
  if grep -qx "$LOCATION" <<<"$locations"; then
    echo "   ok  $pair"
  else
    echo "   MISSING  $pair is not available in $LOCATION"; missing=1
  fi
done
if [ "$missing" = 1 ]; then
  echo
  echo "Some services are not offered in $LOCATION. Run again with another region, e.g.:"
  echo "    LOCATION=westeurope bash bootstrap.sh"
  exit 1
fi

step "Resource group $RESOURCE_GROUP"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
  --tags app=invoice env=dev -o none
RG_ID=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)

step "Key Vault"
VAULT=$(az keyvault list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)
if [ -z "$VAULT" ]; then
  VAULT="kv-invoice-dev-$(openssl rand -hex 3)"
  az keyvault create --name "$VAULT" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" \
    --enable-rbac-authorization true --enabled-for-template-deployment true \
    --retention-days 30 --tags app=invoice env=dev -o none
fi
VAULT_ID=$(az keyvault show --name "$VAULT" --query id -o tsv)
echo "   $VAULT"
ME=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
  --role "Key Vault Secrets Officer" --scope "$VAULT_ID" -o none 2>/dev/null || true

ensure_app() { # ensure_app <display name> -> prints appId
  local id
  id=$(az ad app list --display-name "$1" --query "[0].appId" -o tsv)
  if [ -z "$id" ]; then
    id=$(az ad app create --display-name "$1" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  fi
  az ad sp show --id "$id" -o none 2>/dev/null || az ad sp create --id "$id" -o none
  echo "$id"
}

step "GitHub deployment identity ($DEPLOY_APP_NAME)"
DEPLOY_APP_ID=$(ensure_app "$DEPLOY_APP_NAME")
DEPLOY_SP_ID=$(az ad sp show --id "$DEPLOY_APP_ID" --query id -o tsv)
SUBJECT="repo:${GITHUB_REPO}:environment:${GITHUB_ENVIRONMENT}"
if [ -z "$(az ad app federated-credential list --id "$DEPLOY_APP_ID" \
    --query "[?subject=='$SUBJECT'].name" -o tsv)" ]; then
  az ad app federated-credential create --id "$DEPLOY_APP_ID" --parameters "{
    \"name\": \"github-${GITHUB_ENVIRONMENT}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$SUBJECT\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi
echo "   trusts only: $SUBJECT"
for role in "Contributor" "Role Based Access Control Administrator"; do
  az role assignment create --assignee-object-id "$DEPLOY_SP_ID" \
    --assignee-principal-type ServicePrincipal --role "$role" --scope "$RG_ID" -o none
done
az role assignment create --assignee-object-id "$DEPLOY_SP_ID" \
  --assignee-principal-type ServicePrincipal --role "Key Vault Secrets Officer" \
  --scope "$VAULT_ID" -o none
echo "   rights: this resource group only"

step "Email sending identity ($SMTP_APP_NAME)"
SMTP_APP_ID=$(ensure_app "$SMTP_APP_NAME")
SMTP_SP_ID=$(az ad sp show --id "$SMTP_APP_ID" --query id -o tsv)
if ! az keyvault secret show --vault-name "$VAULT" --name smtp-password -o none 2>/dev/null; then
  SECRET=$(az ad app credential reset --id "$SMTP_APP_ID" --append --display-name smtp \
    --years 2 --query password -o tsv)
  retry 12 az keyvault secret set --vault-name "$VAULT" --name smtp-password \
    --value "$SECRET" -o none
  unset SECRET
  echo "   new secret stored in Key Vault (valid 2 years)"
else
  echo "   secret already in Key Vault"
fi

AZURE_ENV=$(printf '{"clientId":"%s","tenantId":"%s","subscriptionId":"%s","resourceGroup":"%s","location":"%s","keyVault":"%s","smtpAppId":"%s","smtpPrincipalId":"%s"}' \
  "$DEPLOY_APP_ID" "$TENANT_ID" "$SUBSCRIPTION_ID" "$RESOURCE_GROUP" "$LOCATION" "$VAULT" \
  "$SMTP_APP_ID" "$SMTP_SP_ID")

cat <<EOF

==> Done. One last step, in GitHub (no secrets involved; these are identifiers):

  github.com/${GITHUB_REPO} -> Settings -> Secrets and variables -> Actions
  -> "Variables" tab -> "New repository variable"

  Name:  AZURE_ENV
  Value: ${AZURE_ENV}

After that, every push deploys to Azure automatically.
EOF
