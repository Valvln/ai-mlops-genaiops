param location string = 'westeurope'
param storageAccountName string = 'ai300storage${uniqueString(resourceGroup().id)}'
param keyVaultName string = 'ai300kv${uniqueString(resourceGroup().id)}'
param workspaceName string = 'ai300ml${uniqueString(resourceGroup().id)}'

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

// Backs the Application Insights component below. Workspace-based components are
// the only kind still supported, and they require a Log Analytics workspace.
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: 'ai300law${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ai300appi${uniqueString(resourceGroup().id)}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

// No containerRegistry property: the workspace would otherwise provision one,
// and nothing here needs it yet.
resource mlWorkspace 'Microsoft.MachineLearningServices/workspaces@2026-05-01' = {
  name: workspaceName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    storageAccount: storageAccount.id
    keyVault: kv.id
    applicationInsights: applicationInsights.id
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

output storageAccountName string = storageAccount.name
output keyVaultUri string = kv.properties.vaultUri
output workspaceName string = mlWorkspace.name
output workspaceId string = mlWorkspace.id
