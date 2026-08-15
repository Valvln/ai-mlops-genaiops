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

// Added only when a run failed for want of them. Each entry names the run.
var verifiedActions = [
  // Run 31303220508. R2 saw this in the activity log and dropped it, reasoning
  // that it appeared only because a human had run a preview by hand and that
  // the workflow performs none. The reasoning was wrong: `az deployment group
  // create` invokes validate/action itself before submitting. Deducing what a
  // deployment will need is the same mistake as reading it from documentation,
  // and this is the failure that caught it.
  'Microsoft.Resources/deployments/validate/action'

  // Run 31303489048. Both named in the same failure. R2 predicted that reads
  // would surface — the activity log records writes and actions, not reads —
  // but predictions are not entitlements: these enter here because a run
  // demanded them, and the reads on the other three declared types stay out
  // until a failure names them too.
  'Microsoft.KeyVault/vaults/read'
  'Microsoft.OperationalInsights/workspaces/read'

  // Run 31303655969.
  'Microsoft.MachineLearningServices/workspaces/read'

  // Run 31303842799, and the one worth reading twice. That run's deployment
  // SUCCEEDED - ai300-ci-31303842799 is Succeeded in the history - and the
  // workflow still went red, because the CLI could not read the deployment
  // back once it had created it. Green is not proof that something was
  // deployed, which is why SC-001 asks for the record; red is not proof that
  // nothing was, which is why this failure had to be read rather than assumed.
  'Microsoft.Resources/deployments/read'

  // --- Feature 004: the template gained three resource types ----------------
  //
  // Run 31899938698. All three were named by that ONE failure, and this is the
  // detail that corrects an assumption carried since 003.
  //
  // 003 discovered its operations one per run, so 004 predicted the same
  // sequence and budgeted four to seven gated runs for it. That is not how it
  // behaved. The failure came back as InvalidTemplateDeployment - "Deployment
  // failed with multiple errors" - because ARM validates the whole template
  // before submitting any of it, and reports every authorization failure it
  // finds in one response. 003's failures arrived singly because they were
  // discovered during execution, not during validation.
  //
  // The rule is unchanged and still binding: only what a failure NAMES is
  // added. Here one failure named three, so three enter together, sharing a
  // provenance. "One per run" was never the rule - it was a symptom of how the
  // earlier failures happened to surface.
  'Microsoft.Storage/storageAccounts/blobServices/containers/write'
  'Microsoft.MachineLearningServices/workspaces/datastores/write'
  'Microsoft.MachineLearningServices/workspaces/computes/write'
]

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
