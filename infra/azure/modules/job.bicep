// Runs `python -m app.ops.migrate` on demand, before each rollout: creates the restricted app
// role and Keycloak's database if missing, then applies the database migrations.
param location string
param tags object
param environmentId string
param identityId string
param acrLoginServer string
param imageTag string
param keyVaultUri string
param postgresFqdn string
param adminLogin string

var names = ['pg-admin-password', 'app-db-password', 'keycloak-db-password']

resource migrate 'Microsoft.App/jobs@2025-01-01' = {
  name: 'migrate'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
      secrets: [
        for n in names: {
          name: n
          keyVaultUrl: '${keyVaultUri}secrets/${n}'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: '${acrLoginServer}/backend:${imageTag}'
          command: ['python', '-m', 'app.ops.migrate']
          env: [
            { name: 'APP_ENVIRONMENT', value: 'dev' }
            {
              name: 'APP_DATABASE_URL'
              value: 'postgresql+asyncpg://${adminLogin}@${postgresFqdn}:5432/invoice?ssl=require'
            }
            { name: 'APP_DATABASE_PASSWORD', secretRef: 'pg-admin-password' }
            { name: 'APP_DB_ROLE_PASSWORD', secretRef: 'app-db-password' }
            { name: 'KEYCLOAK_DB_PASSWORD', secretRef: 'keycloak-db-password' }
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
    }
  }
}

output name string = migrate.name
