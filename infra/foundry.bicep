// Feature 006 — Azure AI Foundry GenAIOps backbone (AI-300 Domain 3).
//
// A SIBLING OF main.bicep, NOT A MODULE OF IT. The two are deployed
// independently, to different resource groups, in different regions, on
// different schedules. main.bicep's northeurope resource group is not touched
// by anything in this file, and deleting either group leaves the other intact
// (FR-008).
//
// DEPLOYED BY HAND, NOT BY CI. infra-deploy.yml watches infra/** and deploys
// main.bicep only. Routing this feature through that pipeline would mean
// widening the least-privilege CI role to a second resource group and a new
// resource provider, for infrastructure that is meant to be disposable — see
// spec.md Assumptions and infra/DEPLOY.md § 5.

// swedencentral, and the reason is a measurement rather than a preference.
// `az cognitiveservices model list -l northeurope` (2026-08-18) reports every
// chat model there as GlobalProvisionedManaged only — a PTU SKU, whose floor
// is ~316 EUR/day and which cannot be paused, only deleted. The same query
// against swedencentral reports Standard and GlobalStandard. Region
// eligibility for THIS subscription was then confirmed separately and for
// free: a what-if against a minimal accounts probe returned Succeeded/Create,
// with none of the RequestDisallowedByAzure that rules out westeurope
// (infra/DEPLOY.md § 0.2).
param location string = 'swedencentral'

// 'ai300fdry' + 13 characters of uniqueString is 22, well inside the 2-64
// range Cognitive Services account names allow. The name also becomes the
// custom subdomain below, which is GLOBALLY unique — hence uniqueString here
// and not a fixed literal.
param foundryAccountName string = 'ai300fdry${uniqueString(resourceGroup().id)}'

// Fixed, unlike the account name: a project name only has to be unique inside
// its own account, so there is no global collision to defend against.
param foundryProjectName string = 'block3-genaiops'

// The object id of the human who will actually call the deployment and read
// the traces back. Empty by default so the template still deploys without it —
// the infrastructure is valid, it just cannot be USED by anyone until this is
// supplied. Not given a default value because an object id is tenant-specific:
// hard-coding one would make this template silently wrong in any other
// directory, and the failure would surface as a role assignment on a principal
// that does not exist.
param callerPrincipalId string = ''

var commonTags = {
  project: 'ai300-prep'
  environment: 'learning'
}

// --- The Foundry account -----------------------------------------------------
//
// THE POINT OF THIS RESOURCE IS WHAT IT DOES NOT DRAG IN. The alternative
// path — a hub (Microsoft.MachineLearningServices/workspaces, kind 'hub') —
// provisions dependencies on creation, including a container registry that
// bills at rest and, as main.bicep records at length, cannot be detached
// afterwards. This project has already paid for that mechanism twice. The
// account below creates nothing it was not asked to create: no registry, no
// key vault, no storage account (FR-001).
//
// It also bills nothing while idle. An AIServices account is metered on the
// tokens that flow through its deployments; an account with no traffic costs
// EUR 0.00/day. That claim is a success criterion (SC-006), not a footnote —
// it is checked against Cost Management the day after deployment, because
// Cost Management lags ingestion by 8-24 h and an absent row is "no data yet",
// never "confirmed free" (infra/DEPLOY.md § 4).
resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  sku: {
    // The only SKU an AIServices account offers. S0 is a billing MODE
    // (pay-per-call), not a reserved capacity tier — nothing here is the
    // provisioned-throughput commitment that constraint 2 rules out. The
    // per-token/PTU decision is made on the DEPLOYMENT's sku, further down
    // the file, not here.
    name: 'S0'
  }
  identity: {
    // Required before the account can own projects, and the principal the
    // connections below authenticate as.
    type: 'SystemAssigned'
  }
  properties: {
    // Declared, not defaulted. Without it the account is a plain multi-service
    // Cognitive Services resource and `accounts/projects` cannot be created
    // under it — the project resource is what makes this "Foundry" rather than
    // "AI Services".
    allowProjectManagement: true
    // The account's own DNS label under cognitiveservices.azure.com. Required
    // for Entra ID (token) authentication against the data plane: without a
    // custom subdomain the endpoint only accepts keys, which is precisely the
    // thing disableLocalAuth below refuses.
    customSubDomainName: foundryAccountName
    // NO KEYS, ANYWHERE IN THIS FEATURE. call_model.py authenticates with
    // DefaultAzureCredential, so nothing has to be stored, rotated, or kept
    // out of git. Declared rather than left at the service default because a
    // default that silently permits key auth is a credential this repository
    // would then have to manage.
    disableLocalAuth: true
    // Declared for the same reason main.bicep declares it on the registry: an
    // isolation default that moves underneath the template becomes either a
    // cost (a managed network) or a connectivity failure, discovered at the
    // worst moment. The harness runs from a laptop, so public access is what
    // it needs.
    publicNetworkAccess: 'Enabled'
  }
  tags: commonTags
}

// --- The Foundry project -----------------------------------------------------
//
// A child of the account, and free: a project has no meter of its own and no
// independent lifecycle. It is the scope the model deployment, the prompts and
// the traces are organised under, and it is the scope the tracing connection
// has to exist at for the SDK to find it (see data-model.md).
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundryAccount
  name: foundryProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Block 3 — GenAIOps'
    description: 'AI-300 Domain 3: one token-billed deployment, a versioned prompt, a retrievable trace.'
  }
  tags: commonTags
}

// --- The model deployment ----------------------------------------------------
//
// THE MODEL IS NOT THE ONE THE COST MODEL RECOMMENDED, AND THE REASON IS THE
// FINDING. docs/exam-notes/foundry-cost-model.md § 6 picked gpt-5-nano as the
// cheapest usable model in swedencentral, on the strength of
// `az cognitiveservices model list`. A what-if against that choice failed:
//
//   InsufficientQuota — quota limit 0 for OpenAI.GlobalStandard.gpt-5-nano
//
// The catalog answers "does this SKU exist in this region". Only
// `az cognitiveservices usage list` answers "can THIS SUBSCRIPTION deploy it",
// and for gpt-5-nano the answer was a hard zero. The second candidate,
// gpt-4o-mini 2024-07-18, failed differently — ServiceModelDeprecated, retired
// 2026-03-31 — which the catalog also did not volunteer.
//
// gpt-4.1-mini is what survived both checks. Re-verified live on 2026-08-19:
//
//   OpenAI.GlobalStandard.gpt4.1-mini    current 0.0    limit 200.0
//
// Note the meter's spelling. The standard-SKU quota meters write the model as
// `gpt4.1-mini` while the batch meters write `gpt-4.1-mini`, so a usage query
// filtered on the model's real name matches the BATCH rows only and reports a
// healthy quota for a SKU that is not the one being deployed. That is exactly
// the shape of green-looking answer to the wrong question this repository
// keeps having to unlearn.
//
// Lifecycle at deployment time: Legacy, inference deprecation 2027-04-14 —
// deployable now, and a date to re-check rather than a reason to avoid it.
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundryAccount
  name: 'gpt-4.1-mini'
  sku: {
    // THE ONE LINE THIS WHOLE FEATURE'S COST CONSTRAINT RESTS ON, and SC-001
    // does not trust it — the criterion reads the SKU back off the live
    // service with `az cognitiveservices account deployment show`, because
    // what a template requested and what a service provisioned are different
    // facts.
    //
    // GlobalStandard is per-token: the meter runs while a request is in
    // flight and stops when it ends. The PTU family this file must never
    // name — ProvisionedManaged, GlobalProvisionedManaged,
    // DataZoneProvisionedManaged — bills a reserved floor of ~316 EUR/day
    // that cannot be paused and can only be stopped by deleting the
    // deployment (foundry-cost-model.md § 3b).
    name: 'GlobalStandard'
    // Units of 1000 tokens/minute, against a subscription limit of 200. One
    // is the floor, and a rate limit is not a spending limit: capacity caps
    // how fast tokens can be consumed, not how many. What keeps the bill
    // small is the handful of calls this feature makes, not this number.
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      // Pinned. Left unset, the service resolves whatever it considers
      // current, which would make "which model answered this call" a question
      // the trace could not settle — and settling exactly that is User Story
      // 3's job.
      version: '2025-04-14'
    }
    // Explicit rather than defaulted: with a single deployment there is
    // nothing to fail over to, and an upgrade policy that silently moves the
    // model version underneath a pinned trace would defeat the pin above.
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// --- Letting a human actually call it ----------------------------------------
//
// DISCOVERED BY FAILING, with the refusal quoted verbatim. The first run of
// call_model.py against the deployment above, by an account holding Owner on
// the subscription, returned:
//
//   401 PermissionDenied — The principal
//   `ValerioQuaranta@Valvln.onmicrosoft.com` lacks the required data action
//   `Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action`
//   to perform `POST /openai/deployments/{deployment-id}/chat/completions`
//
// This is the Cognitive Services version of a lesson feature 004 already
// learned on storage: OWNER IS A CONTROL-PLANE ROLE. It authorises creating,
// reading and deleting the deployment resource, and authorises nothing at all
// against the data plane behind it. The two permission systems are separate,
// and holding the stronger-sounding one grants nothing in the other.
//
// Cognitive Services OpenAI User is the narrowest built-in role containing the
// action the refusal named — read on the account, plus the inference actions,
// and no write to the resource itself. The repository's standing rule against
// widening with a built-in role governs the CI deployer role in
// infra/ci-identity.bicep, which is untouched here and by this whole feature
// (FR-012 stays dormant); this grant is to the author's own interactive
// identity, at the scope of one account in a disposable resource group.
//
// Declared here rather than run as a one-off `az role assignment create` so it
// comes back with the resource group. This environment is meant to be
// destroyed and rebuilt, and a grant that only exists in someone's shell
// history does not survive that.
var cognitiveServicesOpenAIUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
)

resource callerInferenceGrant 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(callerPrincipalId)) {
  scope: foundryAccount
  name: guid(foundryAccount.id, callerPrincipalId, cognitiveServicesOpenAIUserRoleId)
  properties: {
    roleDefinitionId: cognitiveServicesOpenAIUserRoleId
    principalId: callerPrincipalId
    // 'User', not the 'ServicePrincipal' main.bicep uses: the principal here
    // is a human in the directory, not a managed identity. Declaring it skips
    // a directory lookup either way.
    principalType: 'User'
  }
}

output foundryAccountName string = foundryAccount.name
output foundryAccountEndpoint string = foundryAccount.properties.endpoint
output foundryProjectName string = foundryProject.name
output modelDeploymentName string = modelDeployment.name
