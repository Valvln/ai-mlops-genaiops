# Contract: the deployment role

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

The central contract of this feature. It states exactly what the CI principal may
do, and — the part that matters — **where each permission came from**.

FR-006c: every operation must trace to a derivation-record line or a recorded
verification failure. This file is that record. An operation with an empty
Provenance cell is not permitted to ship.

## Identity of the role

| Property | Value |
| --- | --- |
| Name | `AI300 CI Deployer (rg-ai300-test01)` |
| Type | custom role definition |
| API version | `2022-04-01` |
| Declared in | `infra/ci-identity.bicep` |
| `assignableScopes` | `/subscriptions/<sub>/resourceGroups/rg-ai300-test01` — this and nothing else |
| Assigned to | the service principal of the `ai300-github-deploy` application |
| Assigned at | the same resource group |

`assignableScopes` holding one resource group means the role cannot be assigned
elsewhere even deliberately. It is a second, independent bound on FR-005: the
grant is narrow *and* the role is unusable outside that scope.

## Permitted operations

### Seeded from derivation (R2)

Activity log of deployment `ai300-rbac-002b`, filtered to the deploying caller.
Ten operations were observed; two are dropped as explained below.

| Operation | Provenance | Ships? |
| --- | --- | --- |
| `Microsoft.Resources/deployments/write` | activity log, deployer | yes |
| `Microsoft.Resources/deployments/operationStatuses/read` | activity log, deployer | yes |
| `Microsoft.Storage/storageAccounts/write` | activity log, deployer | yes |
| `Microsoft.KeyVault/vaults/write` | activity log, deployer | yes |
| `Microsoft.OperationalInsights/workspaces/write` | activity log, deployer | yes |
| `Microsoft.Insights/components/write` | activity log, deployer | yes |
| `Microsoft.MachineLearningServices/workspaces/write` | activity log, deployer | yes |
| `Microsoft.Authorization/roleAssignments/write` | activity log, deployer | yes |
| `Microsoft.Resources/deployments/validate/action` | activity log, deployer — but the deployer was a human running a preview | **no** |
| `Microsoft.Resources/deployments/whatIf/action` | same | **no** |

The last two are dropped because the workflow performs no preview. They are
recorded rather than deleted so that adding them later has to be a decision with
a reason, not a quiet re-appearance.

### Excluded, though present in the same log

These were invoked during the same deployment by principals that are **not** the
deployer. Granting them would over-provision the CI principal with authority that
belongs to the platform.

| Operation | Actual caller | Why excluded |
| --- | --- | --- |
| `Microsoft.KeyVault/vaults/accessPolicies/write` | `ai300ml2mgou37pfmjou` (the workspace identity) | authority over who may read the vault; the deployer never invoked it |
| `Microsoft.Insights/diagnosticSettings/write` | `ai300ml2mgou37pfmjou` | the workspace configuring itself |
| `Microsoft.Authorization/roleAssignments/write` | `Azure Machine Learning` (platform) | the platform maintaining its own grant — feature 002, R10 |

### Added by verification — to be filled during implementation

Empty by design. A row is added **only** when a deployment run fails and the
error names the operation. The run id is the evidence; a row without one is
inadmissible under FR-006c.

| Operation | Run that failed for want of it | Error excerpt |
| --- | --- | --- |
| `Microsoft.Resources/deployments/validate/action` | `31303220508` | `AuthorizationFailed … does not have authorization to perform action 'Microsoft.Resources/deployments/validate/action' over scope '…/deployments/ai300-ci-31303220508'` |
| `Microsoft.KeyVault/vaults/read` | `31303489048` | `AuthorizationFailed … 'Microsoft.KeyVault/vaults/read' over scope '…/vaults/ai300kv2mgou37pfmjou'` |
| `Microsoft.OperationalInsights/workspaces/read` | `31303489048` | `AuthorizationFailed … 'Microsoft.OperationalInsights/workspaces/read' over scope '…/workspaces/ai300law2mgou37pfmjou'` |
| `Microsoft.MachineLearningServices/workspaces/read` | `31303655969` | `AuthorizationFailed … 'Microsoft.MachineLearningServices/workspaces/read' over scope '…/workspaces/ai300ml2mgou37pfmjou'` |
| `Microsoft.Resources/deployments/read` | `31303842799` | `AuthorizationFailed … 'Microsoft.Resources/deployments/read' over scope '…/deployments/ai300-ci-31303842799'` |
| `Microsoft.ContainerRegistry/registries/write` | `32112759907` | `InvalidTemplateDeployment … Authorization failed for template resource 'ai300crmxvtm2okukvmy' … does not have permission to perform action 'Microsoft.ContainerRegistry/registries/write'` |
| `Microsoft.ContainerRegistry/registries/operationStatuses/read` | `32113221779` | `AuthorizationFailed … does not have authorization to perform action 'Microsoft.ContainerRegistry/registries/operationStatuses/read' over scope '…/registries/ai300crmxvtm2okukvmy/operationStatuses/registries-2f9168a6-…'` |

**The run that hung instead of failing.** `32113221779` produced no error in its
log at all. It sat in "deploying" for 33 minutes while the registry it was
waiting on had been created and reported `Succeeded` within seconds. The refusal
existed the whole time, in the ARM deployment operation rather than in the run:
`statusCode` `Forbidden` and `statusMessage.status` `Failed`, under a
`provisioningState` of **`Running`**. ARM retries a post-create poll rather than
abandoning it, so a missing read on an async operation status stalls
indefinitely.

Two consequences. A run with no output is a place to look for an authorization
refusal — `az deployment operation group list` is where it is — and not a reason
to keep waiting. And the operation was **not** the predicted one: the prediction
was `registries/read`, the resource; the refusal named the operation-status
endpoint. Adding the prediction would have widened the role and left the
deployment hanging unchanged.

**Feature 004's five operations are in `infra/ci-identity.bicep` but not in this
table.** They cite run `31899938698` in the template's own comments; the rows
were never added here. They are not backfilled from those comments, because a
row's evidence is the error excerpt and that excerpt was not preserved. The gap
is recorded rather than papered over.

**A refusal naming an already-granted operation is about scope, not breadth.**
Runs `32111580715` and `32111854107` failed `AuthorizationFailed` on
`Microsoft.Resources/deployments/validate/action` — row one of this table, held
since `31303220508`. They targeted `rg-ai300-test01` after that group, and with
it the role assignment *and the role definition*, had been deleted. Nothing was
added for them. The change rule below says a failure names the missing
operation; it does not say every named operation is missing.

**Run `31303842799` deployed successfully and reported red.** Its deployment
record is `Succeeded` in the history; the failure came afterwards, when the CLI
tried to read the deployment back. Green is not evidence that something was
deployed — which is why SC-001 asks for the record rather than the colour — and
red is not evidence that nothing was. Both halves of that had to be checked
against the history rather than inferred from the run.

**This one was dropped above, and the drop was wrong.** R2 excluded
`validate/action` by reasoning that it appeared in the activity log only because
the author had run a preview by hand, and that the workflow performs no preview.
The premise held; the conclusion did not. `az deployment group create` invokes
`validate/action` itself before submitting the deployment, so the operation is
required whether or not anybody asks for a preview.

Worth recording plainly rather than quietly correcting: FR-006a forbids taking
operations from documentation, and the reason is that predicting what a
deployment needs is unreliable. That prohibition was honoured — and then the
same unreliable prediction was made in the *opposite* direction, to remove an
operation the log had actually recorded. Deriving is safe because it observes;
subtracting from a derivation is a deduction, and deductions are what the
verification pass exists to catch.

`whatIf/action` remains dropped, and now on better grounds: this run reached the
validation step without it.

Operations *predicted* in R2 as likely to surface — reads on the declared types,
`deployments/read`, `subscriptions/resourceGroups/read`,
`roleDefinitions/read` — are predictions only. They enter this table when
observed, not before, and a prediction that never materialises is simply wrong
and is discarded.

## Not permitted, and asserted so

The role carries no `*` action, no `delete` on any type, and nothing under
`Microsoft.Authorization` beyond `roleAssignments/write` (plus whatever read
verification proves necessary). Each of the following is checked by a probe in
[boundary-probes.md](boundary-probes.md) rather than by reading this file:

- creating a resource type the template does not declare
- acting at subscription scope
- granting authority anywhere

## Change rule

Adding an operation requires a provenance entry in this file. Adding one because
a built-in role contains it, or because it seems likely to be needed, is what
FR-006a forbids — and is the failure mode that produced feature 002's inert
grant.

When `main.bicep` gains a resource type, the first deployment after that change
**will fail**, and the failure is the intended mechanism: it names the missing
operation, which is then added with that run as its provenance.
