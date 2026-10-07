// Invoice platform: the Azure "dev" environment (one resource group).
//
// Deployed in three stages by the GitHub workflow (.github/workflows/deploy.yml):
//   base - network, database, storage, registry, email, Container Apps environment
//   job  - + the database migration job (needs the new images in the registry)
//   apps - + the running apps (after the migration job succeeded)
// Every stage is incremental: running it again changes only what differs.
//
// The resource group and the Key Vault are created once by bootstrap.sh; secrets are
// generated into the vault by the workflow and never appear in this template.

targetScope = 'resourceGroup'

@allowed(['base', 'job', 'apps'])
param stage string = 'base'
param location string = resourceGroup().location
param prefix string = 'invoice'
param envName string = 'dev'
@description('Created by bootstrap.sh; holds every secret.')
param keyVaultName string
@description('Client (application) id of the Entra app used to send email over SMTP.')
param smtpAppId string
@description('Object id of that app\'s service principal.')
param smtpPrincipalId string
@description('Id of the built-in "Communication and Email Service Owner" role (looked up by name).')
param emailRoleId string
@description('Image tag (git commit) to run. Required for the job and apps stages.')
param imageTag string = ''

var tags = {
  app: prefix
  env: envName
}
var suffix = substring(uniqueString(resourceGroup().id), 0, 6)
var adminLogin = 'pgadmin'
var smtpUsername = '${prefix}-${envName}-smtp'

// Built-in role ids.
var roles = {
  acrPull: '7f951dca-d7ab-4bb7-a29b-43e3eb3f2a78'
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// --- identity the apps run as ----------------------------------------------------------

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-${envName}'
  location: location
  tags: tags
}

resource vaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, identity.id, roles.keyVaultSecretsUser)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roles.keyVaultSecretsUser
    )
  }
}

// --- logs ------------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}-${envName}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// --- network ---------------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${prefix}-${envName}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.40.0.0/16'] }
    subnets: [
      {
        name: 'snet-apps'
        properties: {
          addressPrefix: '10.40.0.0/23'
          delegations: [
            {
              name: 'apps'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: '10.40.4.0/28'
          delegations: [
            {
              name: 'postgres'
              properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' }
            }
          ]
        }
      }
    ]
  }
}

var postgresName = 'pg-${prefix}-${envName}-${suffix}'

resource postgresDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: '${postgresName}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource postgresDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: postgresDns
  name: 'vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

// --- database --------------------------------------------------------------------------

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    location: location
    name: postgresName
    subnetId: '${vnet.id}/subnets/snet-postgres'
    privateDnsZoneId: postgresDns.id
    adminLogin: adminLogin
    adminPassword: vault.getSecret('pg-admin-password')
    tags: tags
  }
  dependsOn: [postgresDnsLink]
}

// --- files (PDFs, logos) ---------------------------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${prefix}${envName}${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Only Entra identities (the app's managed identity), never account keys.
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: 30 }
    containerDeleteRetentionPolicy: { enabled: true, days: 30 }
  }
}

resource filesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'files'
  properties: { publicAccess: 'None' }
}

resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, roles.blobDataContributor)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roles.blobDataContributor
    )
  }
}

// --- container registry ----------------------------------------------------------------

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${prefix}${envName}${suffix}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource registryPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, roles.acrPull)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// --- email (Azure Communication Services, Azure-managed sender domain) -----------------

resource emailService 'Microsoft.Communication/emailServices@2023-04-01' = {
  name: 'ecs-${prefix}-${envName}-${suffix}'
  location: 'global'
  tags: tags
  properties: { dataLocation: 'Europe' }
}

resource emailDomain 'Microsoft.Communication/emailServices/domains@2023-04-01' = {
  parent: emailService
  name: 'AzureManagedDomain'
  location: 'global'
  tags: tags
  properties: {
    domainManagement: 'AzureManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communication 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: 'acs-${prefix}-${envName}-${suffix}'
  location: 'global'
  tags: tags
  properties: {
    dataLocation: 'Europe'
    linkedDomains: [emailDomain.id]
  }
}

// The SMTP Entra app (created by bootstrap.sh) may send through this resource. Microsoft
// recommends assigning the role on the resource itself, not inherited.
resource smtpRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: communication
  name: guid(communication.id, smtpPrincipalId, emailRoleId)
  properties: {
    principalId: smtpPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', emailRoleId)
  }
}

// Links that app to the resource; the SMTP login is this username + the app's secret.
resource smtpUser 'Microsoft.Communication/communicationServices/smtpUsernames@2025-09-01' = {
  parent: communication
  name: smtpUsername
  properties: {
    username: smtpUsername
    entraApplicationId: smtpAppId
    tenantId: tenant().tenantId
  }
  dependsOn: [smtpRole]
}

// --- Container Apps environment --------------------------------------------------------

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'cae-${prefix}-${envName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/snet-apps'
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

// --- migration job and apps (need images) ----------------------------------------------

module job 'modules/job.bicep' = if (stage != 'base') {
  name: 'job'
  params: {
    location: location
    tags: tags
    environmentId: environment.id
    identityId: identity.id
    acrLoginServer: registry.properties.loginServer
    imageTag: imageTag
    keyVaultUri: vault.properties.vaultUri
    postgresFqdn: postgres.outputs.fqdn
    adminLogin: adminLogin
  }
  dependsOn: [registryPull, vaultSecretsUser]
}

module apps 'modules/apps.bicep' = if (stage == 'apps') {
  name: 'apps'
  params: {
    location: location
    tags: tags
    environmentId: environment.id
    defaultDomain: environment.properties.defaultDomain
    identityId: identity.id
    identityClientId: identity.properties.clientId
    acrLoginServer: registry.properties.loginServer
    imageTag: imageTag
    keyVaultUri: vault.properties.vaultUri
    postgresFqdn: postgres.outputs.fqdn
    storageAccountUrl: storage.properties.primaryEndpoints.blob
    smtpUsername: smtpUsername
    smtpFrom: 'DoNotReply@${emailDomain.properties.mailFromSenderDomain}'
  }
  dependsOn: [registryPull, vaultSecretsUser, storageBlobContributor, smtpUser, filesContainer]
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output communicationServiceId string = communication.id
output appUrl string = 'https://invoice.${environment.properties.defaultDomain}'
output authUrl string = 'https://auth.${environment.properties.defaultDomain}'
