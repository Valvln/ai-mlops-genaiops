// The authority continuous integration deploys with.
//
// Deliberately NOT part of main.bicep. main.bicep is what CI deploys, and CI
// cannot be the thing that grants CI its own authority. Creating a role
// definition is also outside the resource group this principal is confined to,
// so the split is forced rather than stylistic — see research.md, R8.
//
// Deployed by the author, never by CI:
//   az deployment group create -g rg-ai300-test01 \
//     --template-file infra/ci-identity.bicep \
//     --parameters principalId=<service principal object id>

targetScope = 'resourceGroup'

@description('Object id of the service principal continuous integration authenticates as. Not the application (client) id: a role assignment against a client id points at a principal that does not exist.')
param principalId string

// Every action below traces to a line in specs/003-ci-oidc-deploy/contracts/
// role-definition.md. That file is the record FR-006c makes binding: an action
// with no provenance entry does not ship, and is deleted rather than argued for.
//
// The set is seeded from the activity log of deployment ai300-rbac-002b,
// FILTERED TO THE DEPLOYING CALLER. Filtering is not tidying: the same log
// records three operations invoked by the workspace's own identity and by the
// Azure Machine Learning platform principal, one of which is authority over who
// may read the vault. Taking the log unfiltered would have granted all three.
//
// It is known-incomplete by construction — the activity log records writes and
// actions, not most reads. What it missed surfaces as a deployment failure that
// names the operation, and only then is that operation added, with the failing
// run as its provenance.
var derivedActions = [
  'Microsoft.Resources/deployments/write'
  'Microsoft.Resources/deployments/operationStatuses/read'
  'Microsoft.Storage/storageAccounts/write'
  'Microsoft.KeyVault/vaults/write'
  'Microsoft.OperationalInsights/workspaces/write'
  'Microsoft.Insights/components/write'
  'Microsoft.MachineLearningServices/workspaces/write'
  // main.bicep declares a role assignment on the vault. Without this the
  // deployment cannot complete — and granting it is exactly why the scope
  // below matters: probe P3 proves the principal cannot use it anywhere else.
  'Microsoft.Authorization/roleAssignments/write'
]

// Added only when a run failed for want of them. Empty until that happens.
var verifiedActions = []

resource ciDeployerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'ai300-ci-deployer')
  properties: {
    roleName: 'AI300 CI Deployer (${resourceGroup().name})'
    description: 'Deploys infra/main.bicep from GitHub Actions. Operations discovered by observation, not from documentation - see specs/003-ci-oidc-deploy/contracts/role-definition.md.'
    type: 'CustomRole'
    // One resource group, and nothing else. A second, independent bound on
    // FR-005: even an Owner cannot assign this role anywhere but here.
    assignableScopes: [
      resourceGroup().id
    ]
    permissions: [
      {
        actions: union(derivedActions, verifiedActions)
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

// Name derived with guid() so redeployment is idempotent - the mechanics
// feature 002 established, reused here.
resource ciDeployerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, ciDeployerRole.id)
  properties: {
    roleDefinitionId: ciDeployerRole.id
    principalId: principalId
    // Declared to avoid a directory lookup the deploying identity may not be
    // permitted to make.
    principalType: 'ServicePrincipal'
  }
}

output roleDefinitionId string = ciDeployerRole.id
output roleName string = ciDeployerRole.properties.roleName
output assignmentName string = ciDeployerAssignment.name
