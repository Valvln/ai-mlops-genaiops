param location string = 'westeurope'
param location string = 'northeurope'
param storageAccountName string = 'ai300storage${uniqueString(resourceGroup().id)}'
param keyVaultName string = 'ai300kv${uniqueString(resourceGroup().id)}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

resource kv 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      name: 'standard'
      family: 'A'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

output storageAccountName string = storageAccount.name
output keyVaultUri string = kv.properties.vaultUri
