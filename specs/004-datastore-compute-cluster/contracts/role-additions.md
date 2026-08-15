# Contract: operations added to the deployment role by feature 004

**Feature**: `004-datastore-compute-cluster` · **Date**: 2026-08-15

Continues the record established by
[003's role definition contract](../../003-ci-oidc-deploy/contracts/role-definition.md),
whose rule this feature inherits unchanged:

> **An operation with an empty Provenance cell is not permitted to ship.**

Feature 003 discovered the role's operations by deploying and reading what was
refused. Feature 004 is the first time that role meets a template declaring
resource types it has never seen, which is the situation 003 predicted and wrote
down. The method is the same and is not negotiable here: **the failing run names
the operation, and only the operation it names is added.**

## The rule, restated because this is where it gets tested

1. Deploy. Read the error.
2. Add **exactly** the operation quoted in the `AuthorizationFailed` message to
   `verifiedActions` in `infra/ci-identity.bicep`.
3. Record the run id in this file as its provenance, in the same commit.
4. Redeploy `ci-identity.bicep` as the author. Re-run the workflow.
5. Repeat until green.

**Not permitted**, and each for a reason this repository has already paid for:

| Shortcut | Why not |
| --- | --- |
| Adding the predicted operations up front | The prediction is not evidence. 003's R2 dropped an operation by reasoning about what a deployment "would" need and was wrong; the failure that caught it is now provenance line one. |
| Assigning a built-in role to end the failures | `Contributor` would end the interruption and end the property the role exists for. 003's boundary probe P4 would begin to *succeed*, and its `boundary` job would go red for a good reason. |
| Adding a whole resource type's operations because one was refused | Reads and writes surface separately, one run apart. Granting `*/read` alongside a refused `*/write` grants something no failure demanded. |

## Predicted, pending, ships only when a run names it

Reproduced from [research.md § R6](../research.md). **This table grants
nothing.** It exists so a failure is recognised in seconds, and so that a
failure *not* on this list is noticed as interesting rather than shrugged at.

| # | Predicted operation | Confidence | Run id | Ships? |
| --- | --- | --- | --- | --- |
| 1 | `Microsoft.Storage/storageAccounts/blobServices/containers/write` | high | 31899938698 | ✅ shipped |
| 2 | `Microsoft.MachineLearningServices/workspaces/datastores/write` | high | 31899938698 | ✅ shipped |
| 3 | `Microsoft.MachineLearningServices/workspaces/computes/write` | high | 31899938698 | ✅ shipped |
| 4 | `Microsoft.Storage/storageAccounts/blobServices/containers/read` | medium | — | **never demanded** |
| 5 | `Microsoft.MachineLearningServices/workspaces/datastores/read` | medium | 31899938698 att. 2 | ✅ shipped |
| 6 | `Microsoft.MachineLearningServices/workspaces/computes/read` | medium | 31899938698 att. 2 | ✅ shipped |
| 7 | `Microsoft.Storage/storageAccounts/blobServices/read` | low | — | **never demanded** |

A row moves to the table below when, and only when, a run id fills its cell.

## Confirmed by a failing run — the operations that actually shipped

### Run 31899938698 — 2026-08-15

The first deployment after the merge, as predicted, and the first time the
narrow role met a template declaring types it had never seen.

| Operation | Named by | Date |
| --- | --- | --- |
| `Microsoft.Storage/storageAccounts/blobServices/containers/write` | run 31899938698 | 2026-08-15 |
| `Microsoft.MachineLearningServices/workspaces/datastores/write` | run 31899938698 | 2026-08-15 |
| `Microsoft.MachineLearningServices/workspaces/computes/write` | run 31899938698 | 2026-08-15 |

The error, quoted, with the subscription and client id masked by the runner:

```text
ERROR: {"code": "InvalidTemplateDeployment", "message": "Deployment failed with
multiple errors: 'Authorization failed for template resource
'ai300st2mgou37pfmjou/default/training-data' of type
'Microsoft.Storage/storageAccounts/blobServices/containers'. The client '***'
with object id '1a327ac2-ea18-43d0-9948-0488c72d5eea' does not have permission
to perform action 'Microsoft.Storage/storageAccounts/blobServices/containers/write'
at scope '.../containers/training-data'.
:Authorization failed for template resource 'ai300ml2mgou37pfmjou/ai300_training_data'
of type 'Microsoft.MachineLearningServices/workspaces/datastores'. ... does not have
permission to perform action 'Microsoft.MachineLearningServices/workspaces/datastores/write' ...
:Authorization failed for template resource 'ai300ml2mgou37pfmjou/ai300-cpu-cluster'
of type 'Microsoft.MachineLearningServices/workspaces/computes'. ... does not have
permission to perform action 'Microsoft.MachineLearningServices/workspaces/computes/write' ...'"}
```

**Three operations from one failure, which corrects an assumption.** Feature 003
discovered its operations one per run, and this feature's research predicted the
same rhythm — four to seven gated runs, one operation each. Wrong. The response
code is `InvalidTemplateDeployment`, not `AuthorizationFailed`: ARM validated the
**whole template** before submitting any of it and reported every authorization
failure it found at once. 003's failures arrived singly because they surfaced
during execution rather than during validation.

The binding rule is untouched — **only what a failure names is added** — and it
was satisfied: one failure named three operations, so three were added, sharing
one provenance. "One operation per run" was never the rule; it was a symptom of
how the earlier failures happened to surface, mistaken for a law.

**A confirmed prediction is still not an entitlement.** Rows 1–3 were predicted
with high confidence and they shipped — but they shipped because run 31899938698
named them, not because the table guessed right. Rows 4–7 remain pending and
ship only on the same terms.

### Run 31899938698, attempt 2 — 2026-08-15

The writes cleared validation; two reads then failed during **execution**. The
error code is `DeploymentFailed` with details, not `InvalidTemplateDeployment` —
which confirms the split observed in attempt 1: pre-flight validation catches
writes, reads surface when the deployment actually runs.

| Operation | Named by | Date |
| --- | --- | --- |
| `Microsoft.MachineLearningServices/workspaces/computes/read` | run 31899938698 att. 2 | 2026-08-15 |
| `Microsoft.MachineLearningServices/workspaces/datastores/read` | run 31899938698 att. 2 | 2026-08-15 |

#### The two refusals arrived in different shapes, and that is the finding

```text
{"code":"AuthorizationFailed",
 "message":"The client '***' with object id '1a327ac2-…' does not have
  authorization to perform action
  'Microsoft.MachineLearningServices/workspaces/computes/read' over scope
  '…/computes/ai300-cpu-cluster' or the scope is invalid."}

{"code":"UserError",
 "message":"Identity(object id: 1a327ac2-…) does not have permissions for
  Microsoft.MachineLearningServices/workspaces/datastores/read actions.",
 "additionalInfo":[{"type":"ComponentName","info":{"value":"managementfrontend"}},
                   {"type":"InnerError","info":{"value":{"code":"ForbiddenError"}}}]}
```

The first is ARM's familiar `AuthorizationFailed`. The second is a **`UserError`
raised by the Azure ML `managementfrontend`**, with `ForbiddenError` buried in an
inner error and the operation named in prose rather than in an `action` field.

**Grepping the log for `AuthorizationFailed` finds one and misses the other.**
That would have added a single operation, sent the workflow round again, and
produced an identical failure — costing a whole extra gated approval to
rediscover something already printed in the log that had been read too narrowly.

This is the repository's oldest recurring lesson arriving in a new costume:
*read the captured error, not the summary.* Here the trap is subtler than
usual — both errors were captured, in the same response, and the one that could
be missed is the one that does not use ARM's vocabulary. **A refusal is not
obliged to announce itself in the words you searched for.** The service sitting
in front of the resource gets to phrase its own.

### Two predictions were never demanded

Rows 4 and 7 — `blobServices/containers/read` and `blobServices/read` — never
appeared in any failure, so **they were never added**. The container is created
and never read back by the deployment; the ML control plane reads its own child
resources but ARM does not read the storage ones.

They stay in the predicted table marked *never demanded*, rather than being
quietly deleted. A prediction that did not fire is evidence about how the
deployment behaves, and erasing it would leave the record looking like the
forecast was perfect. It was 5 for 7.

### The object id in the error is the service principal's, not the application's

The error names object id `1a327ac2-ea18-43d0-9948-0488c72d5eea`. The role
assignment's `principalName` is `39fecb6c-26e3-42f3-bef6-0483f7daf6d5`. These are
not in conflict: the first is the **service principal object id**, the second the
**application (client) id**. `DEPLOY.md` § 5 warns that assigning a role against
the client id points at a principal that does not exist — this is the same
distinction seen from the other side, and confirms the failing principal is the
one holding the role.

## Predicted **not** to fail

| Operation | Why it should already be held |
| --- | --- |
| `Microsoft.Authorization/roleAssignments/write` | Added by 003 for the Key Vault assignment in `main.bicep`. The new container grant needs the same operation at a scope inside the same resource group. |

If the container grant fails on authorisation anyway, that is **not** a routine
addition — it would mean the operation is scope-sensitive in a way 003 did not
observe, and it gets written up rather than patched.

## Closing check

Before this feature closes, all three must hold:

- [ ] Every operation added to `ci-identity.bicep` during feature 004 has a run
      id in the confirmed table above.
- [ ] The count of rows in the confirmed table equals the count of operations
      added to `verifiedActions` by this feature.
- [ ] The `boundary` job of `infra-deploy.yml` is still green — the role was
      widened by exactly what was refused, and not by more.

The third is the one that matters. The first two can both pass while the role
has quietly become too wide, because they only count what was *written down*.
The boundary job is the check that pushes against the boundary instead of
reading it — the distinction 002's SC-003 failed on.
