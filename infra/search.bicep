// Feature 008 — the search service block 5 measures retrieval quality on
// (AI-300 Domain 5).
//
// A SIBLING OF foundry.bicep, NOT PART OF IT, and the separation is deliberate
// rather than tidy. foundry.bicep carries a success criterion that says it can
// be deployed twice in a row without a manual step in between; folding a new
// resource type into that file would make the second deployment's outcome a
// statement about two things at once. Deployed into the same resource group, so
// one `az group delete` still disposes of the whole environment.
//
// DEPLOYED BY HAND, NOT BY CI, for the same reason foundry.bicep is: CI's
// least-privilege identity has no Microsoft.Search operations and deploys
// main.bicep only. Adding a resource type here does not change that, and the
// CI role is untouched by this feature.

// swedencentral, and here the region is load-bearing twice over.
//
// FREE-TIER SEMANTIC RANKING IS REGIONAL, WHICH THE FEATURE MATRIX STATES ONLY
// IN A FOOTNOTE. Sweden Central carries the footnote that says semantic ranker
// is available on the free tier; northeurope — this repository's documented
// default region everywhere else — does not carry it, and carries a different
// footnote instead: high demand prevents the creation of new search services
// there at all. So the region that would normally be assumed here is
// disqualified on two independent grounds, and neither of them is visible to
// `az bicep build`.
param location string = 'swedencentral'

// Lowercase letters, digits and dashes only, 2-60 characters, and GLOBALLY
// unique: the name becomes the host in <name>.search.windows.net. Hence
// uniqueString, as on the Foundry account. 9 + 13 = 22 characters.
param searchServiceName string = 'ai300srch${uniqueString(resourceGroup().id)}'

// The object id of the human who will create the index, push documents and read
// service statistics. Empty by default so the template still deploys without it:
// the service is valid, it just cannot be USED by anyone until this is supplied.
// Not defaulted to a literal, because an object id is tenant-specific and a
// hard-coded one would make this template silently wrong in another directory.
param callerPrincipalId string = ''

var commonTags = {
  project: 'ai300-prep'
  environment: 'learning'
}

// --- The service -------------------------------------------------------------
//
// EUR 0.00/day, and that is the whole design constraint. Basic — the next tier
// up, and the one every tutorial assumes — is EUR 2.13/day and bills at rest
// whether or not a query is ever issued, with no way to pause it short of
// deletion (docs/exam-notes/rag-cost-model.md). The spec's response to that was
// to reduce the scope until it fitted the free tier, rather than to raise the
// tier until it fitted the scope: one index, ~145 chunks, and a comparison of
// query shapes rather than of index configurations.
//
// What the tier costs in exchange is measured rather than assumed — reading the
// service's own limits back off /servicestats is User Story 2, and it exists
// because the published quota table has columns for Basic through L2 and no
// column for Free.
resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'free'
  }
  identity: {
    // Present for symmetry with the Foundry account and for nothing else. The
    // free tier grants no managed identity for INDEXER outbound connections,
    // which is one of the two reasons this feature pushes documents itself
    // instead of using integrated vectorization — see
    // specs/008-rag-retrieval-quality/contracts/search-service-and-index.md § 4.
    type: 'SystemAssigned'
  }
  properties: {
    // The only values the free tier accepts. Declared rather than defaulted so
    // that a future edit raising either one fails here, where it is cheap, and
    // not against a live service.
    replicaCount: 1
    partitionCount: 1
    // HighDensity exists to pack many small indexes into one service and is
    // standard3-only. 'Default' is the only option at this tier.
    //
    // CAPITALISED, AND THE REST REFERENCE SPELLS IT LOWERCASE. The ARM template
    // reference for this resource type documents the enum as `default` /
    // `highDensity`; the Bicep type definition declares it as
    // 'Default' | 'HighDensity' | null and emits BCP036 on the lowercase form.
    // The service accepts either, so this is a warning rather than an error and
    // easy to leave in place — but a warning left in place is how a real one
    // stops being read (docs/exam-notes are corrected on the same principle).
    hostingMode: 'Default'
    // 'free' IS A DISTINCT PLAN FROM 'disabled' AND FROM 'standard', and the
    // middle value is the one this feature needs. 'standard' is the billed
    // semantic ranker (EUR ~0.85 per 1000 queries) and requires Basic or above,
    // so setting it here would not just cost money, it would not deploy.
    // 'free' allows 1000 semantic queries per month at no charge and stops with
    // a billing error rather than a charge when the allowance is spent — which
    // is exactly the failure mode this repository wants: refuse, do not bill.
    // Without this line the property defaults to 'disabled' and the fourth
    // retrieval method in the comparison would silently be unavailable.
    semanticSearch: 'free'
    // NO KEYS, ANYWHERE IN THIS FEATURE, matching the Foundry account. Every
    // data-plane call — creating the index, pushing documents, querying, and
    // reading /servicestats by hand with curl — carries an Entra ID token.
    //
    // WARNING FOR ANY LATER EDIT: authOptions and disableLocalAuth are mutually
    // exclusive. Setting both is not a redundant belt-and-braces declaration,
    // it is a template that will not deploy. authOptions is therefore omitted
    // entirely rather than set to an RBAC-flavoured value.
    disableLocalAuth: true
    // Declared for the reason foundry.bicep gives: an isolation default that
    // moves underneath the template becomes either a cost — a private endpoint
    // is a billed resource — or a connectivity failure discovered at the worst
    // moment. The harness runs from a laptop.
    publicNetworkAccess: 'enabled'
  }
  tags: commonTags
}

// --- Letting a human actually use it -----------------------------------------
//
// TWO ROLES, AND THE NON-OBVIOUS ONE IS THE ADMINISTRATIVE-SOUNDING ONE.
//
// The instinct is that Search Index Data Contributor — the data-plane role —
// covers everything a script does. It does not: the permission matrix gives
// "access quotas and service statistics" to Owner, Contributor and Search
// Service Contributor only. /servicestats is the entire measurement behind User
// Story 2, so the data role alone would produce a 403 that reads convincingly
// like a free-tier restriction and is nothing of the kind.
//
// OWNER IS NOT ENOUGH EITHER, exactly as it was not on Cognitive Services. It is
// a control-plane role here too: it can create this service and read its keys,
// and it cannot create an index or load a single document. The lesson has now
// been paid for on storage, on Cognitive Services, and here.
//
// Both assigned BY GUID rather than by display name, and declared in the
// template rather than run as one-off `az role assignment create` calls, so they
// come back with the resource group. A grant that only exists in someone's shell
// history does not survive a teardown, and this environment is meant to be
// destroyed and rebuilt.
var searchServiceContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
)

var searchIndexDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
)

// Creates the index, and reads the service's quotas and statistics.
resource callerServiceGrant 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(callerPrincipalId)) {
  scope: searchService
  name: guid(searchService.id, callerPrincipalId, searchServiceContributorRoleId)
  properties: {
    roleDefinitionId: searchServiceContributorRoleId
    principalId: callerPrincipalId
    // A human in the directory, not a managed identity. Declaring it skips a
    // directory lookup that would otherwise happen at deployment time.
    principalType: 'User'
  }
}

// Pushes documents, and issues the four query shapes the comparison is made of.
resource callerDataGrant 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(callerPrincipalId)) {
  scope: searchService
  name: guid(searchService.id, callerPrincipalId, searchIndexDataContributorRoleId)
  properties: {
    roleDefinitionId: searchIndexDataContributorRoleId
    principalId: callerPrincipalId
    principalType: 'User'
  }
}

output searchServiceName string = searchService.name
output searchEndpoint string = 'https://${searchService.name}.search.windows.net'
