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
| 1 | `Microsoft.Storage/storageAccounts/blobServices/containers/write` | high | — | pending |
| 2 | `Microsoft.MachineLearningServices/workspaces/datastores/write` | high | — | pending |
| 3 | `Microsoft.MachineLearningServices/workspaces/computes/write` | high | — | pending |
| 4 | `Microsoft.Storage/storageAccounts/blobServices/containers/read` | medium | — | pending |
| 5 | `Microsoft.MachineLearningServices/workspaces/datastores/read` | medium | — | pending |
| 6 | `Microsoft.MachineLearningServices/workspaces/computes/read` | medium | — | pending |
| 7 | `Microsoft.Storage/storageAccounts/blobServices/read` | low | — | pending |

A row moves to the table below when, and only when, a run id fills its cell.

## Confirmed by a failing run — the operations that actually shipped

*Empty at the time of writing. This is the deliverable of the deployment phase.*

| Operation | Run id | The error, quoted | Date |
| --- | --- | --- | --- |
| | | | |

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
