# Research: Deployment from continuous integration, without a stored secret

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

Everything below was resolved against the live subscription, the live GitHub
API, or current documentation on the date above. Nothing is quoted from memory.
Where a finding was produced by a command, the command is given so it can be
re-run.

---

## R1 — Baseline: what is deployed today

```bash
az resource list -g rg-ai300-test01 --query "[].type" -o tsv
```

| Resource | Type |
| --- | --- |
| `ai300st2mgou37pfmjou` | `Microsoft.Storage/storageAccounts` |
| `ai300law2mgou37pfmjou` | `Microsoft.OperationalInsights/workspaces` |
| `ai300kv2mgou37pfmjou` | `Microsoft.KeyVault/vaults` |
| `ai300appi2mgou37pfmjou` | `Microsoft.Insights/components` |
| `ai300ml2mgou37pfmjou` | `Microsoft.MachineLearningServices/workspaces` |
| `Application Insights Smart Detection` | `microsoft.insights/actiongroups` |

**Six resources**, unchanged from the count feature 002 recorded. The action
group is platform-created and declared by no template; 002 already established
this. It is the SC-002 baseline.

Subscription `5900fbc9-…` in tenant `38d1879a-…`. One resource group exists:
`rg-ai300-test01`, in `northeurope`. **This confirms the clarification decision**
that a second resource group must be created as a probe target — there is
currently no other named scope to be refused against.

The author holds **Owner at subscription scope**, and nothing else. That is what
makes the setup steps possible, and it is also why the boundary probes cannot be
run from the author's machine: they would all succeed.

---

## R2 — The operations the deployment actually invoked (derivation pass)

This is FR-006a's first pass, and it works. Two sources, one much better than the
other.

### Source 1: deployment operations — resource types, not operation names

```bash
az deployment operation group list -g rg-ai300-test01 -n ai300-rbac-002b \
  --query "[].{prov:properties.provisioningOperation, type:properties.targetResource.resourceType}"
```

Gives the resource types touched and whether each was a Read or a Create, but not
the RBAC operation strings. Useful as a cross-check, insufficient on its own.

### Source 2: the activity log — the actual operation strings

```bash
az monitor activity-log list -g rg-ai300-test01 \
  --start-time 2026-08-08T06:20:00Z --end-time 2026-08-08T06:45:00Z \
  --query "[?authorization.action!=null].{action:authorization.action, caller:caller}" -o tsv | sort -u
```

This names operations exactly as a role definition needs them.

### The trap: the activity log records every caller, not just the deployer

Filtering by caller is not tidying — it is the difference between a correct role
and an over-granted one:

| Operation | Caller | Whose? |
| --- | --- | --- |
| `Microsoft.Resources/deployments/write` | `ValerioQuaranta@…` | **the deployer** |
| `Microsoft.Resources/deployments/validate/action` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.Resources/deployments/whatIf/action` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.Resources/deployments/operationStatuses/read` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.Storage/storageAccounts/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.KeyVault/vaults/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.OperationalInsights/workspaces/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.Insights/components/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.MachineLearningServices/workspaces/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.Authorization/roleAssignments/write` | `ValerioQuaranta@…` | the deployer |
| `Microsoft.KeyVault/vaults/accessPolicies/write` | `85e8321f-…` | **not the deployer** |
| `Microsoft.Insights/diagnosticSettings/write` | `85e8321f-…` | **not the deployer** |
| `Microsoft.Authorization/roleAssignments/write` | `b57b41f8-…` | **not the deployer** |

Resolving the two foreign callers:

```bash
az ad sp show --id 85e8321f-1e51-42cb-8ced-7fca9b51498b --query displayName -o tsv
az ad sp show --id b57b41f8-5286-4549-a5b4-d98e7254cd80 --query displayName -o tsv
```

- `85e8321f-…` → **`ai300ml2mgou37pfmjou`** — the workspace's own system-assigned
  identity, writing vault access policies and diagnostic settings for itself.
- `b57b41f8-…` → **`Azure Machine Learning`** — the platform service principal,
  writing a role assignment.

That last row is feature 002's R10 finding, visible in the activity log: the
platform granting the workspace identity a role, on its own initiative, during a
deployment. **The identity 002 proved is not ours to control is writing into the
same log we are deriving from.** Taking the log unfiltered would hand the CI
principal three operations it never performed — including
`vaults/accessPolicies/write`, which is authority over who can read the vault.

**Decision**: the derivation set is the activity log **filtered to the deploying
caller**. Provenance is recorded per operation in
[contracts/role-definition.md](contracts/role-definition.md).

### Two operations dropped from the derived set

`validate/action` and `whatIf/action` appear only because the author ran a
preview by hand. The workflow will not preview — FR-010 wants a real deployment
and SC-002 verifies the inventory directly, so a preview earns nothing and would
cost two operations. **Decision: the workflow runs the deployment only.** If a
preview is wanted later, the role gains those operations with that change as
their provenance.

### Why a second pass is still required

The activity log records writes and actions. It does **not** record most reads,
and it does not record the reads ARM performs to resolve a deployment. The
derived set is therefore known-incomplete by construction, which is exactly why
FR-006a specifies verification by deployment. Operations expected to surface —
recorded here as **predictions, not entitlements**, and admissible only if an
observed failure names them:

- reads on each declared resource type (the deployment did `Read` before `Create`
  on the workspace and the vault, per Source 1)
- `Microsoft.Resources/deployments/read`
- `Microsoft.Resources/subscriptions/resourceGroups/read`
- `Microsoft.Authorization/roleDefinitions/read`, to resolve the role the
  template's own assignment references

---

## R3 — The trust condition, and a format change that would have cost a session

GitHub's OIDC subject claim historically reads
`repo:OWNER/REPO:environment:NAME`. That is **not** the format this repository
produces.

```bash
gh api repos/Valvln/ai-mlops-genaiops -q '{repo_id: .id, owner_id: .owner.id, created: .created_at}'
# {"created":"2026-08-05T16:35:59Z","owner_id":188171957,"repo_id":1324268843}
```

GitHub's documentation states that repositories **created after 15 July 2026**
use an immutable subject format carrying numeric owner and repository ids:

```text
repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:NAME
```

This repository was created **2026-08-05**, three weeks after the cutover. The
expected subject is therefore:

```text
repo:Valvln@188171957/ai-mlops-genaiops@1324268843:environment:azure-deploy
```

Writing the conventional format would produce a federated credential that never
matches. The failure surfaces as `AADSTS70021: No matching federated identity
record found`, which reads like a typo in the environment name and would be
debugged in the wrong place.

**Decision — do not construct the subject from documentation either.** The first
workflow run requests a token and prints **only** its `sub`, `aud` and `iss`
claims; the federated credential is created from the observed value. This is the
same discipline FR-006a applies to the role, applied to the trust condition:
observation over documentation, including over the documentation consulted above.

**The token itself is never printed** — only the three claims are decoded out of
it. At that point in the sequence no federated credential exists, so the token
cannot be exchanged for anything, but the habit is worth keeping.

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange` (what `azure/login` requests)

---

## R4 — Custom role definitions

**Cost: none.** Role definitions and role assignments are control-plane metadata
and carry no charge. The tenant currently holds zero custom roles
(`az role definition list --custom-role-only true` → `0`), so no limit is near.

**A custom role may include `Microsoft.Authorization/roleAssignments/write`.**
This matters: the template declares a role assignment on the vault, so without it
the deployment cannot complete. Microsoft's guidance explicitly describes
creating a custom role holding only that operation, in preference to the broader
built-in roles. The built-in `Role Based Access Control Administrator` was
inspected for comparison:

```bash
az role definition list --name "Role Based Access Control Administrator" --query "[0].permissions"
# actions: roleAssignments/write, roleAssignments/delete, */read, Microsoft.Support/*
```

`*/read` across the whole assignable scope, plus delete. Narrower than
`Contributor`, still far wider than this deployment needs — and the pair
`Contributor` + this role was the alternative rejected by the FR-006
clarification.

- API version: `Microsoft.Authorization/roleDefinitions` → **`2022-04-01`** is the
  latest non-preview (`az provider show -n Microsoft.Authorization`). Same
  version already used for `roleAssignments` in `main.bicep`.
- `assignableScopes` will contain only the resource group id, so the definition
  cannot be assigned anywhere else even by an Owner who tried.

---

## R5 — The approval gate

GitHub environments with protection rules are **free on public repositories**:
*"Users with GitHub Free plans can only configure environments for public
repositories."* This repository is public (`"visibility":"public"`), so the gate
costs nothing. Up to six required reviewers may be configured.

**`Prevent self-review` must be left off.** There is one author; enabling it would
make every deployment permanently unapprovable. This is the concrete form of the
spec's edge case — the gate is a deliberate pause, not a separation of duties,
and the setting is where that distinction becomes visible.

The environment is the load-bearing control, not decoration: the federated
credential's subject names it (R3), so a run that has not entered the environment
cannot obtain a token at all. The gate is enforced by Entra, not only by GitHub.

---

## R6 — Fork pull requests

Documented behaviour for `pull_request` from a fork: *"The `GITHUB_TOKEN` has
read-only permissions in pull requests from forked repositories"* and *"with the
exception of `GITHUB_TOKEN`, secrets are not passed to the runner when a workflow
is triggered from a forked repository."*

`id-token: write` therefore cannot be obtained from a fork pull request, because
the whole permission set is capped at read. Three independent things would each
have to fail for a fork to deploy:

1. the deploying workflow does not subscribe to any `pull_request` event;
2. a fork run cannot be granted `id-token: write`;
3. even holding a token, the subject would name a `pull_request` context, not
   `environment:azure-deploy`, and Entra would refuse the exchange.

The existing validation workflow needs no change to keep working: it requests
`contents: read` and reads nothing else. It will be extended only to build every
template under `infra/`, so `ci-identity.bicep` is validated too (Principle V).
That adds no credential and no token permission.

---

## R7 — Choosing the boundary probes

Every probe must produce an **authorization** refusal (FR-017a) against a
**named** target (FR-017b), and must create nothing billable in the event it
unexpectedly succeeds. Two constraints narrowed the choice more than expected.

**Unregistered providers are disqualified.** A resource type whose provider is
not registered fails with `MissingSubscriptionRegistration`, which is not an
authorization refusal and is worthless as evidence.

```bash
az provider list --query "[?registrationState=='Registered'].namespace" -o tsv
```

`Microsoft.Network` is **not registered** on this subscription, which rules out
the obvious "create a virtual network" probe.

**The chosen undeclared-type probe is `Microsoft.ManagedIdentity/userAssignedIdentities`.**
Its provider is registered, a user-assigned identity carries no charge even if
one were created, and the template declares nothing of that type. There is an
incidental symmetry worth noting: it is the exact resource type feature 002
deferred to the teardown as an untested hypothesis. Here it appears as something
the CI principal must be **refused**.

| # | Boundary tested | Probe | Free if it succeeded? |
| --- | --- | --- | --- |
| 1 | write at subscription scope | create a resource group | yes |
| 2 | another named container | read `rg-ai300-probe` | read-only |
| 3 | granting authority outside scope | assign a role at subscription scope | yes, metadata |
| 4 | undeclared type inside scope | create a user-assigned identity in `rg-ai300-test01` | yes |

Probe 2 requires `rg-ai300-probe` to **exist**, created by the author. That is
FR-017b's reason: against a resource group that does not exist, a refusal cannot
be told apart from an absence.

**Decision: the probes run as assertions inside the workflow, not as a one-off
capture.** Each asserts a non-zero exit *and* an authorization error code; a
probe that succeeds turns the run red. This makes SC-003 a standing regression
test rather than a screenshot — if the boundary is ever widened, a deployment
fails and says so. Specified in
[contracts/boundary-probes.md](contracts/boundary-probes.md).

---

## R8 — Where the identity's own grant lives

The custom role and its assignment cannot live in `main.bicep`: that is the
template CI deploys, and CI cannot be the thing that grants CI its authority.
They also cannot be created by CI at all — FR-005 keeps the principal inside one
resource group, and creating a role definition is a subscription-level act.

Entra objects (the application, its service principal, the federated credential)
are not ARM resources and cannot be expressed in Bicep at all. The split is
therefore forced, and it is worth stating plainly rather than discovering:

| Object | Created by | How |
| --- | --- | --- |
| Application, service principal, federated credential | the author | `az ad` commands, recorded in the runbook |
| Custom role definition, role assignment | the author | `infra/ci-identity.bicep`, deployed by the author |
| Everything in `main.bicep` | continuous integration | the deploying workflow |

`ci-identity.bicep` takes the principal's object id as a parameter, so no
directory identifier is written into the template.

---

## R9 — Versions, pinned

| Component | Version | How resolved |
| --- | --- | --- |
| `azure/login` | `v3.0.1` → `858f4093d287a904987dfd22abd163280f939550` | `gh api repos/Azure/login/releases/latest` |
| `actions/checkout` | `v4` → `11d5960a326750d5838078e36cf38b85af677262` | `gh api repos/actions/checkout/git/ref/tags/v4` |
| Bicep CLI (local) | `0.46.1` | `az bicep version` |
| `Microsoft.Authorization/roleDefinitions` | `2022-04-01` | latest non-preview on the live provider |
| `Microsoft.Authorization/roleAssignments` | `2022-04-01` | unchanged from `main.bicep` |

**Actions are pinned to commit SHAs, not tags.** A tag can be repointed by
whoever controls the action; this workflow holds an identity that can write to
the subscription, and the whole feature is an argument about not extending trust
further than necessary. The readable tag is kept in a trailing comment so the
pin can be audited. `azure/login@v3.0.1` was published 2026-08-04, five days
before this plan — recorded because a five-day-old release is worth knowing about
when the pin is reviewed.

---

## R10 — Storing the identifiers

`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` are identifiers,
not credentials: possessing all three grants nothing without a token from the
trusted issuer bearing the matching subject. SC-004's third refusal exists to
prove precisely that.

They will nonetheless be stored as repository **secrets** rather than variables.
Storing them as variables would advertise the honest claim — that they are inert
— but it also publishes a tenant and subscription identifier on a public
repository for no gain. Secrets are the conventional home, cost nothing, and
weaken no requirement: FR-001 forbids storing a *credential*, and these are not
credentials whichever box they sit in.

One consequence to record, because the spec's Assumptions section says these
values "appear in run logs as a matter of course": stored as secrets they will be
**masked** in logs. The claim about their nature stands; the incidental claim
about their visibility does not, and SC-004 is what settles the question either
way.

---

## Summary of decisions

| # | Decision | Basis |
| --- | --- | --- |
| R1 | Six-resource baseline; second resource group needed | live inventory |
| R2 | Derivation = activity log **filtered by caller**; preview operations dropped | live activity log, callers resolved |
| R3 | Immutable subject format; subject read from an observed token | repo created 2026-08-05, after the cutover |
| R4 | Custom role at `2022-04-01`, `assignableScopes` = the resource group | live provider, current guidance |
| R5 | GitHub environment as the gate; self-review left enabled | free on public repos; one author |
| R6 | Validation workflow extended to build every template, no credential | documented fork restrictions |
| R7 | Four probes, all registered providers, all free-if-successful, run as assertions | live provider registration |
| R8 | Entra objects by CLI, role objects by `ci-identity.bicep`, both author-run | Bicep cannot express Entra objects |
| R9 | Actions pinned to SHAs | trust minimisation |
| R10 | Identifiers stored as secrets, and why that is not a contradiction | FR-001 forbids credentials, not identifiers |
