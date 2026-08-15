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

// INERT TODAY, AND DELIBERATELY SO. Read this before assuming it does anything.
//
// The platform separately grants this same identity **Key Vault Administrator**
// on this same vault, which subsumes secret read entirely. Nothing depends on
// the assignment below: remove it and the workspace loses no access whatsoever.
//
// It is kept for two reasons. It is the only role assignment this repository
// actually owns and can deploy - the storage equivalent cannot be declared at
// all, see the note above - so it is where the working mechanics live: a name
// derived with guid() so redeployment is idempotent, principalType declared to
// avoid a directory lookup, and the role id reached through
// subscriptionResourceId() so no subscription id is written down. And it is the
// fallback if the platform's grants are ever narrowed.
//
// If that ever stops being true - if the platform's vault grant disappears -
// this becomes load-bearing. Until then it documents an intent, not a control.
resource keyVaultSecretsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, mlWorkspace.id, keyVaultSecretsUserRoleId)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: mlWorkspace.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Where data lives, and what runs on it (feature 004) ---------------------
// Until now this template declared a workspace that could hold nothing and run
// nothing. The four resources below are the two things a training job needs -
// a place to read from and a target to run on - plus the grant that connects
// them.

// A container of our own rather than the one the workspace creates for its own
// housekeeping. Training data and workspace system artifacts sharing a location
// would work today and would make "clear the workspace state" and "delete the
// training data" the same operation.
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' existing = {
  parent: storageAccount
  name: 'default'
}

resource trainingContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  // Fixed rather than derived from uniqueString(): container names are scoped
  // to the account, so the global collision that forced derived names on the
  // storage account and the vault cannot arise here. A stable name is one the
  // job asset can reference without a parameter.
  name: 'training-data'
  properties: {
    // Declared, not defaulted. "The default is private" is the kind of thing
    // that is true until it is not, and anonymous read would defeat the whole
    // identity-based design below.
    publicAccess: 'None'
  }
}

// The datastore is metadata: it holds no data and costs nothing. What makes it
// worth declaring is the one property below.
resource trainingDatastore 'Microsoft.MachineLearningServices/workspaces/datastores@2026-05-01' = {
  parent: mlWorkspace
  name: 'ai300_training_data'
  properties: {
    datastoreType: 'AzureBlob'
    accountName: storageAccount.name
    containerName: trainingContainer.name
    protocol: 'https'
    // Resolved from the deployment's cloud rather than written as a literal.
    endpoint: environment().suffixes.storage
    // THE LOAD-BEARING PROPERTY. 'None' reads like "unset"; it is a decision.
    // It makes the datastore credential-less: no account key, no SAS, and
    // nothing cached in the workspace's key vault for anyone with vault access
    // to retrieve later. Access is decided at the storage account by RBAC,
    // which is what makes the role assignment further down meaningful.
    credentials: {
      credentialsType: 'None'
    }
    description: 'Training data. Identity-based access: no key, no SAS.'
  }
}

// The first resource in this repository billed by the hour - and the shape that
// makes that survivable. See docs/exam-notes/compute-cost-model.md for the
// measured rates behind every number in these comments.
resource cpuCluster 'Microsoft.MachineLearningServices/workspaces/computes@2026-05-01' = {
  parent: mlWorkspace
  name: 'ai300-cpu-cluster'
  location: location
  identity: {
    // Not decoration. Three identities could perform a datastore read - the
    // submitting user, the workspace, and the compute - and without one here
    // the reader is whichever the service picks. This one is also the only
    // identity in this deployment whose grants this repository owns: feature
    // 002 established that the workspace identity's grants are the platform's
    // to maintain and cannot be reduced.
    type: 'SystemAssigned'
  }
  properties: {
    computeType: 'AmlCompute'
    description: 'Training and batch scoring. Rests at zero nodes.'
    properties: {
      // Chosen against QUOTA, not against the price list. Standard_A1_v2 is
      // cheaper (0.03598 EUR/h) and is offered by `az ml compute list-sizes` -
      // and its family quota on this subscription is 0, so it can never
      // allocate. Supported by the service and allocatable here are different
      // questions, answered by different commands.
      //   DS1_v2: 1 vCPU, 3.5 GB, 0.05774 EUR/node-hour.
      //   2 nodes x 1 vCPU = 2 vCPU, against a DSv2 family limit of 6 and a
      //   regional dedicated total of 20.
      vmSize: 'Standard_DS1_v2'
      // Not low priority, and not by preference: the regional low-priority
      // quota on this subscription is 0. Every low-priority family reports a
      // limit of -1, which reads as "no limit" and is gated by that regional
      // total. The per-family row is the wrong row to read.
      vmPriority: 'Dedicated'
      osType: 'Linux'
      remoteLoginPortPublicAccess: 'Disabled'
      scaleSettings: {
        // The property that makes the cluster free at rest, and the whole
        // reason a cluster was chosen over a compute instance - which costs
        // ~25 EUR/month while merely STOPPED, for a disk and a load balancer
        // that stopping does not release.
        //
        // Note what this is: a REQUEST. That the cluster actually rests at zero
        // is verified after deployment by reading the node counts back from the
        // service. This line is not evidence for it.
        minNodeCount: 0
        // Bounds a runaway job at ~2.77 EUR/day. Two rather than one so that
        // batch scoring across nodes stays demonstrable.
        maxNodeCount: 2
        // Equal to the service default, and declared anyway: the requirement is
        // that the value be chosen. 120 s at this size is 0.002 EUR of billed
        // tail per job - irrelevant as money, and it is the mechanism the exam
        // asks about. Shortening it would make closely spaced jobs re-allocate
        // nodes, which costs more wall clock than the tail costs money.
        nodeIdleTimeBeforeScaleDown: 'PT120S'
      }
    }
  }
}

// Storage Blob Data Reader. Verified against the live tenant on 2026-08-15.
var storageBlobDataReaderRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
)

// LOAD-BEARING. Verified by withdrawal on 2026-08-15, not assumed.
//
// Unlike the Key Vault assignment above - which is kept and documented as inert
// because the platform grants the same access anyway - this one does real work,
// and it was tested rather than trusted:
//
//   Grant removed  -> job stoic_zoo_rrf7805s9q FAILED at the data mount with
//                     ScriptExecution.StreamAccess.Authentication, and the
//                     underlying request logged HTTP 403 against
//                     .../training-data/sample.csv (server request id
//                     df3c1698-401e-0004-7bd8-2cfcaa000000).
//   Grant restored -> the job succeeds again.
//
// The result was not the expected one, and the reason is worth keeping. The
// WORKSPACE identity holds Storage Blob Data Contributor at storage ACCOUNT
// scope, which covers this container, so the grant below looked likely to be
// redundant. It is not - because the job runs as the COMPUTE cluster's identity
// (job.yml declares `identity: managed`), and a grant held by one principal does
// not authorise a read performed by another. The grant that matters is the one
// held by the identity the job actually runs as.
//
// Scoped to the container rather than the storage account: the narrowest scope
// that works, and it keeps the cluster out of the workspace's own containers.
resource clusterContainerReadGrant 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: trainingContainer
  name: guid(trainingContainer.id, cpuCluster.id, storageBlobDataReaderRoleId)
  properties: {
    roleDefinitionId: storageBlobDataReaderRoleId
    principalId: cpuCluster.identity.principalId
    // Skips a directory lookup against a principal that may be seconds old.
    // This is feature 002's PrincipalNotFound lesson, and it is why a
    // newly created identity does not fail intermittently here.
    principalType: 'ServicePrincipal'
  }
}

output storageAccountName string = storageAccount.name
output keyVaultUri string = kv.properties.vaultUri
output workspaceName string = mlWorkspace.name
output workspaceId string = mlWorkspace.id
output trainingContainerName string = trainingContainer.name
output trainingDatastoreName string = trainingDatastore.name
output computeClusterName string = cpuCluster.name
