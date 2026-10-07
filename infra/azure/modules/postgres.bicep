// PostgreSQL Flexible Server on a private subnet (no public access), TLS only.
param location string
param name string
param subnetId string
param privateDnsZoneId string
param adminLogin string
@secure()
param adminPassword string
param sku string
param tier string
param zone string
param tags object

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku // dev default Standard_B1ms (burstable): the cheapest, fine for testing
    tier: tier
  }
  properties: {
    version: '16'
    availabilityZone: empty(zone) ? null : zone
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: subnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

// The app's first migration uses the citext extension; Azure requires allow-listing it.
resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: 'CITEXT'
    source: 'user-override'
  }
}

// The databases themselves ("invoice", "keycloak") are created by the migration job, so the
// admin owns them.

output fqdn string = server.properties.fullyQualifiedDomainName
