// Not westeurope: that region rejects new subscriptions with
// RequestDisallowedByAzure ("not accepting new customers").
param location string = 'northeurope'
// Prefix kept short: storage account names cap at 24 characters, and
// uniqueString() already consumes 13 of them.
param storageAccountName string = 'ai300st${uniqueString(resourceGroup().id)}'
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
    // Declared rather than left to the service default: an isolation mode of
    // AllowOnlyApprovedOutbound provisions a managed Azure Firewall, billed
    // hourly whether or not anything uses it. what-if does not reveal the
    // default, so it is pinned here instead of discovered after the fact.
    managedNetwork: {
      isolationMode: 'Disabled'
    }
    // The system datastores authenticated with account keys, which meant the
    // identity needed listKeys on the storage account — a control-plane
    // permission much broader than reading and writing the data itself.
    // Identity mode removes the need for keys altogether, so the two role
    // assignments below become the whole of what the workspace uses.
    systemDatastoresAuthMode: 'identity'
    // The platform grants this identity a role over the entire resource group
    // unless told not to. Declaring false is the supported way to stop it, and
    // is what keeps the reduction from being quietly undone by a future
    // deployment. Discovered only because what-if showed the property; it is
    // invisible from the template alone.
    //
    // The warning below is suppressed, not absent. The property is real - it
    // was read back from the deployed workspace - but no generally available
    // API version publishes it in its Bicep type definitions, checked against
    // 2024-10-01 through 2026-05-01. Bicep sends unrecognised properties
    // through to the provider unchanged, so the declaration takes effect; what
    // it loses is compile-time checking of this one line. Re-test on a later
    // API version and remove the suppression once the type catches up.
    #disable-next-line BCP037
    allowRoleAssignmentOnRG: false
  }
  tags: {
    project: 'ai300-prep'
    environment: 'learning'
  }
}

// --- Workspace identity permissions -----------------------------------------
// This template declares ONE permission. The identity holds several more, all
// maintained by the platform, none of them declarable here — see the note below
// and infra/DEPLOY.md for why the attempt to declare them failed and what was
// learned from it.
//
// Built-in role definition identifier, verified against the live tenant.
// subscriptionResourceId() derives the subscription from the deployment
// context, so no subscription id is written down here.
var keyVaultSecretsUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

// Blob data access is NOT declared here, and that is a finding rather than an
// omission. It was declared, and the deployment failed with
// RoleAssignmentExists.
//
// What happened, from the assignment timestamps: deleting the grant the
// platform had made caused the platform to recreate it, under a new random
// name, within the same deployment. The template's own assignment - same
// identity, same role, same scope, different name - was then rejected as a
// duplicate. It can never succeed while the workspace keeps a system-assigned
// identity, because the platform actively maintains that grant.
//
// Declaring it would therefore guarantee that every future deployment of this
// template fails. The identity does hold blob data access; it is simply the
// platform's grant, not one this repository controls. See infra/DEPLOY.md.

// Read only, and currently redundant: the platform separately grants this
// identity broader authority over the vault, so nothing depends on this
// assignment today. It is kept because it is the one permission this template
// does own and does successfully declare, and because it is what the workspace
// would fall back on if the platform's grants were ever narrowed.
resource keyVaultSecretsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, mlWorkspace.id, keyVaultSecretsUserRoleId)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: mlWorkspace.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output storageAccountName string = storageAccount.name
output keyVaultUri string = kv.properties.vaultUri
output workspaceName string = mlWorkspace.name
output workspaceId string = mlWorkspace.id
