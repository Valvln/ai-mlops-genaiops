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
  // FIRST LINK OF A CHAIN THAT EXISTS ONLY TO STOP ARM WORKING IN PARALLEL.
  // Every child of a Cognitive Services account mutates the account, and Azure
  // serializes those writes and rejects the loser with RequestConflict. Nothing
  // here reads the model deployment; the dependency is purely an ordering
  // constraint. See findings.md § F1 — and note the first attempt at this fix
  // ordered the project against the CONNECTION only, whereupon the project
  // raced the DEPLOYMENT instead. The pairs are not the point; the parallelism
  // is, so the children are chained one after another rather than paired up.
  dependsOn: [
    modelDeployment
  ]
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
    // Units of 1000 tokens/minute, against a subscription limit of 200. A
    // rate limit is not a spending limit: capacity caps how fast tokens can
    // be consumed, not how many. What keeps the bill small is the handful of
    // calls these features make, not this number — raising it costs nothing
    // at rest on a per-token SKU, where capacity is a throttle rather than
    // the reserved floor it would be on a provisioned one.
    //
    // WAS 1, AND ONE WAS TOO FEW TO RUN AN EVALUATOR. Measured 2026-08-23
    // (specs/007-genai-eval-observability/findings.md § F3): capacity 1 buys
    // ONE REQUEST PER MINUTE, not just 1000 tokens per minute. Block 3 never
    // noticed because its calls were manual and minutes apart. Block 4 scores
    // a response by calling a judge model, so it makes at least two calls per
    // scored answer and 429s on contact.
    capacity: 10
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

// --- Where traces go (User Story 3) ------------------------------------------
//
// FOUNDRY HAS NO TRACE STORE OF ITS OWN. That is the finding behind these two
// resources, not an architectural preference: the portal's tracing view is a
// reader over a connected Application Insights resource, and if nothing is
// connected there is nothing to read. Making a call retrievable AFTER THE FACT
// — the whole of User Story 3 — therefore means owning the store the call is
// written to (research.md § R6).
//
// Neither resource bills at rest, and that was checked rather than assumed.
// The Retail Prices API for swedencentral publishes no per-hour or
// per-instance meter for either type; every meter is consumption-priced
// (Standard Data Analyzed EUR 2.0208/GB, retention EUR 0.1142/GB/month beyond
// the free 31 days), and the first 5 GB/month of ingestion is free. This
// feature emits kilobytes. Both rows were added to spec.md's Cost table before
// this code was written, which is the order constraint 4 requires.
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: 'ai300fdrylaw${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    // Equal to the free retention allowance, and declared rather than
    // defaulted for exactly that reason: retention beyond 31 days is the one
    // line item here that could turn a free workspace into a billed one, and
    // a default that moves is how that happens unnoticed.
    retentionInDays: 30
  }
  tags: commonTags
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ai300fdryappi${uniqueString(resourceGroup().id)}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    // Workspace-based, which is the only kind still supported — a classic
    // component would have its own retention and its own bill.
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: 30
  }
  tags: commonTags
}

// --- Connecting the store to the project -------------------------------------
//
// THE ONE API VERSION IN THIS TEMPLATE THAT WAS NOT VERIFIED IN ADVANCE.
// research.md § R3 and § R6 flagged 2025-04-01-preview as sourced from a
// public GitHub sample of unknown age rather than from this subscription, and
// tasks.md T018 carried that flag forward as the last open assumption in the
// plan. It is settled by `az bicep build` and `az deployment group what-if`
// against the live subscription before this file is deployed, never by the
// sample being cited — the difference between "compiles" and "the provider
// accepts it" is a distinction this repository has already paid for twice.
//
// Two connections, not one: the account-level one is what the portal's own
// tracing surface reads, the project-level one is what a project-scoped client
// resolves. Both were verified to exist after deployment by listing them
// through the ARM connections API.
//
// WHAT THE HARNESS DOES *NOT* DO WITH THEM, AND WHY. The obvious use for the
// project connection is
// `AIProjectClient(...).telemetry.get_application_insights_connection_string()`
// — let the app discover its own telemetry target instead of being told. That
// was tried and refused:
//
//   PermissionDenied — The principal ... lacks the required data action
//   `Microsoft.CognitiveServices/accounts/AIServices/connections/read`
//
// Closing it would cost more than it buys. The only built-in role carrying
// that action is Cognitive Services User, whose dataActions are
// `Microsoft.CognitiveServices/*` — the whole data plane, for one lookup. A
// one-action custom role would be narrow, but a roleDefinition is an
// authorization-provider object, not a resource-group one: it would survive
// `az group delete` and leave exactly the kind of residue SC-007 asserts is
// absent. So call_model.py takes the connection string from the App Insights
// resource directly, and these connections stay what they are — the wiring the
// PORTAL reads, deployed and verified, not something the harness depends on.
var appInsightsConnectionName = '${foundryAccountName}-appinsights'

resource accountAppInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundryAccount
  name: appInsightsConnectionName
  // SERIALIZED AGAINST THE PROJECT ON PURPOSE, AND NOT BECAUSE IT READS
  // ANYTHING FROM IT. Both this connection and the project are children of the
  // account and both mutate it, so ARM issues them concurrently and Azure
  // rejects whichever loses:
  //
  //   RequestConflict — Another operation is in progress on the resource
  //   '.../accounts/ai300fdry...'
  //
  // Measured 2026-08-23 (findings.md § F1), on this file unchanged, when the
  // project lost. Feature 006 deployed the same template cleanly on
  // 2026-08-19 — the race simply resolved the other way. Neither
  // `az bicep build` nor `what-if` can see this: both describe the desired
  // state, and the defect is in the order the writes are attempted.
  //
  // Third link in the chain: account -> deployment -> project -> here.
  dependsOn: [
    foundryProject
  ]
  properties: {
    category: 'AppInsights'
    target: applicationInsights.id
    // ApiKey is the connection's OWN auth type — how the Foundry resource
    // authenticates to Application Insights — and is unrelated to
    // disableLocalAuth above, which governs how callers authenticate to the
    // Foundry data plane. The key is the App Insights connection string,
    // resolved from the resource at deploy time rather than written down: it
    // never appears in this file, in git, or in a deployment parameter.
    authType: 'ApiKey'
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
  }
}

// NAMED DIFFERENTLY FROM ITS ACCOUNT-LEVEL SIBLING, AND THAT IS THE FIX.
// Giving both the same name is what made this template one-shot: a project is
// projected as an AML workspace that shares the account's connection
// namespace, so the second of the two to be created collides with the first —
//
//   UserError — Connection ai300fdry...-appinsights already exist, and can only
//   be updated by the workspace that created it, which is the workspace with
//   workspaceId: .../Microsoft.MachineLearningServices/workspaces/...@AML
//
// Feature 006 did not hit this because the race in F1 happened to create the
// project-level one first; once F1's chain fixed the ordering, the collision
// surfaced every run (findings.md § F2). The names are now distinct, so
// neither connection can be mistaken for the other's prior version.
var projectAppInsightsConnectionName = '${appInsightsConnectionName}-project'

resource projectAppInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: foundryProject
  name: projectAppInsightsConnectionName
  // Last link in the chain. Being a child of the project already orders this
  // after the project, but not after the account-level connection — which is
  // its sibling in everything that matters to ARM, and its rival for the same
  // account-level lock.
  dependsOn: [
    accountAppInsightsConnection
  ]
  properties: {
    category: 'AppInsights'
    target: applicationInsights.id
    authType: 'ApiKey'
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
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
