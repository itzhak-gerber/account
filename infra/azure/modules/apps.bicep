// The running parts: web (nginx + the app), backend API, background worker, Keycloak, Redis.
// Secrets are never written into this template: each app reads them from Key Vault with its
// managed identity, by name.
param location string
param tags object
param environmentId string
param defaultDomain string
param identityId string
param identityClientId string
param acrLoginServer string
param imageTag string
param keyVaultUri string
param postgresFqdn string
param storageAccountUrl string
param smtpUsername string
param smtpFrom string

var appHost = 'invoice.${defaultDomain}'
var appUrl = 'https://${appHost}'
var authUrl = 'https://auth.${defaultDomain}'

var identity = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${identityId}': {}
  }
}
var registries = [
  {
    server: acrLoginServer
    identity: identityId
  }
]

func secrets(names array, kvUri string, id string) array =>
  map(names, n => {
    name: n
    keyVaultUrl: '${kvUri}secrets/${n}'
    identity: id
  })

var backendSecretNames = [
  'app-db-password'
  'redis-password'
  'web-client-secret'
  'app-secret-key'
  'smtp-password'
  'vapid-private-key'
]

var backendEnv = [
  { name: 'APP_ENVIRONMENT', value: 'dev' }
  { name: 'APP_PUBLIC_URL', value: appUrl }
  {
    name: 'APP_DATABASE_URL'
    value: 'postgresql+asyncpg://invoice_app@${postgresFqdn}:5432/invoice?ssl=require'
  }
  { name: 'APP_DATABASE_PASSWORD', secretRef: 'app-db-password' }
  { name: 'APP_REDIS_URL', value: 'redis://redis:6379/0' }
  { name: 'APP_REDIS_PASSWORD', secretRef: 'redis-password' }
  { name: 'APP_OIDC_ISSUER', value: '${authUrl}/realms/invoice' }
  { name: 'APP_OIDC_CLIENT_SECRET', secretRef: 'web-client-secret' }
  { name: 'APP_SECRET_KEY', secretRef: 'app-secret-key' }
  { name: 'APP_SMTP_HOST', value: 'smtp.azurecomm.net' }
  { name: 'APP_SMTP_PORT', value: '587' }
  { name: 'APP_SMTP_USE_TLS', value: 'true' }
  { name: 'APP_SMTP_USERNAME', value: smtpUsername }
  { name: 'APP_SMTP_PASSWORD', secretRef: 'smtp-password' }
  { name: 'APP_VAPID_PRIVATE_KEY', secretRef: 'vapid-private-key' }
  { name: 'APP_EMAIL_FROM', value: 'חשבוניות <${smtpFrom}>' }
  { name: 'APP_STORAGE_BACKEND', value: 'azure' }
  { name: 'APP_AZURE_STORAGE_ACCOUNT_URL', value: storageAccountUrl }
  { name: 'APP_AZURE_CLIENT_ID', value: identityClientId }
  // Requests reach the backend through nginx with Host "backend".
  { name: 'APP_MCP_ALLOWED_HOSTS', value: '["backend", "backend:*", "${appHost}"]' }
  { name: 'APP_MCP_ALLOWED_ORIGINS', value: '["${appUrl}"]' }
]

resource redis 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'redis'
  location: location
  tags: tags
  identity: identity
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      secrets: secrets(['redis-password'], keyVaultUri, identityId)
      ingress: {
        external: false
        transport: 'tcp'
        targetPort: 6379
        exposedPort: 6379
      }
    }
    template: {
      containers: [
        {
          name: 'redis'
          image: '${acrLoginServer}/redis:7-alpine'
          command: ['/bin/sh', '-c']
          args: ['exec redis-server --requirepass "$REDIS_PASSWORD" --save "" --appendonly no']
          env: [{ name: 'REDIS_PASSWORD', secretRef: 'redis-password' }]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource keycloak 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'auth'
  location: location
  tags: tags
  identity: identity
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      secrets: secrets(
        ['keycloak-db-password', 'keycloak-admin-password', 'web-client-secret', 'smtp-password'],
        keyVaultUri,
        identityId
      )
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'keycloak'
          image: '${acrLoginServer}/keycloak:${imageTag}'
          env: [
            {
              name: 'KC_DB_URL'
              value: 'jdbc:postgresql://${postgresFqdn}:5432/keycloak?sslmode=require'
            }
            { name: 'KC_DB_USERNAME', value: 'keycloak' }
            { name: 'KC_DB_PASSWORD', secretRef: 'keycloak-db-password' }
            { name: 'KC_HOSTNAME', value: authUrl }
            { name: 'KC_BOOTSTRAP_ADMIN_USERNAME', value: 'admin' }
            { name: 'KC_BOOTSTRAP_ADMIN_PASSWORD', secretRef: 'keycloak-admin-password' }
            { name: 'JAVA_OPTS_KC_HEAP', value: '-XX:MaxRAMPercentage=60 -XX:InitialRAMPercentage=30' }
            // Filled into the realm on first import.
            { name: 'APP_PUBLIC_URL', value: appUrl }
            { name: 'INVOICE_WEB_CLIENT_SECRET', secretRef: 'web-client-secret' }
            { name: 'SMTP_HOST', value: 'smtp.azurecomm.net' }
            { name: 'SMTP_PORT', value: '587' }
            { name: 'SMTP_USERNAME', value: smtpUsername }
            { name: 'SMTP_PASSWORD', secretRef: 'smtp-password' }
            { name: 'SMTP_FROM', value: smtpFrom }
          ]
          // Dev size: enough for a few users; startup is slower, hence the longer startup probe.
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health/started', port: 9000 }
              initialDelaySeconds: 20
              periodSeconds: 10
              failureThreshold: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: 9000 }
              periodSeconds: 10
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: 9000 }
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource backend 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'backend'
  location: location
  tags: tags
  identity: identity
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      secrets: secrets(backendSecretNames, keyVaultUri, identityId)
      // Reachable only inside the environment (nginx calls http://backend).
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
        allowInsecure: true
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${acrLoginServer}/backend:${imageTag}'
          env: backendEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/api/v1/health', port: 8000 }
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [redis]
}

resource worker 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'worker'
  location: location
  tags: tags
  identity: identity
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      secrets: secrets(backendSecretNames, keyVaultUri, identityId)
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: '${acrLoginServer}/backend:${imageTag}'
          command: ['arq', 'app.jobs.worker.WorkerSettings']
          env: backendEnv
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      // Exactly one: it also runs the daily jobs (overdue check, summaries).
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [redis]
}

resource web 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'invoice'
  location: location
  tags: tags
  identity: identity
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'web'
          image: '${acrLoginServer}/frontend:${imageTag}'
          env: [{ name: 'BACKEND_URL', value: 'http://backend' }]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [backend]
}

output appUrl string = appUrl
output authUrl string = authUrl
