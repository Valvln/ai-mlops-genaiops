# Contract: the boundary probes

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

Four commands that **must fail**. They satisfy SC-003, and they run as assertions
inside the workflow rather than as a one-time capture, so the boundary is checked
on every deployment instead of on the day it was built.

## Assertion rule

A probe passes when **both** hold:

1. the command exits non-zero, and
2. its stderr names an authorization refusal — `AuthorizationFailed`,
   `AuthorizationFailedWithLinkedSubscription`, or an equivalent `403`.

A probe **fails the workflow run** when the command succeeds. That is the point:
if the boundary is ever widened, a deployment goes red and names the probe that
got through.

Exit non-zero for any other reason is also a failure, and deliberately so —
FR-017 excludes a bad name, an absent target, or an unregistered provider as
evidence. A probe that fails with `MissingSubscriptionRegistration` or
`ResourceGroupNotFound` proves nothing and must be treated as a broken test, not
a held boundary.

## The probes

All four run as the CI principal, inside the deploying workflow, after the
deployment step. All four create nothing billable in the event they unexpectedly
succeed — checked in R7 before being chosen.

### P1 — write at subscription scope

```bash
az group create --name rg-ai300-denied-probe --location northeurope
```

| | |
| --- | --- |
| Boundary | the principal holds nothing above its resource group |
| Expected | non-zero, `AuthorizationFailed` |
| If it succeeded | a resource group exists that should not; free, but delete it and treat the run as failed |

### P2 — a named container other than the declared one

```bash
az group show --name rg-ai300-probe
```

| | |
| --- | --- |
| Boundary | the principal cannot reach another resource group |
| Expected | non-zero, `AuthorizationFailed` |
| Precondition | **`rg-ai300-probe` must exist**, created by the author |
| If it succeeded | read-only, nothing to clean up; the run still fails |

The precondition is FR-017b. Against a resource group that does not exist, a
refusal cannot be distinguished from an absence, and the evidence is void. A
listing — `az group list` — is explicitly **not** used here: the platform filters
enumerations by permission, so it would return an empty set with exit code zero,
which FR-017a rules out as evidence.

### P3 — granting authority outside the scope

```bash
az role assignment create \
  --role Reader \
  --assignee-object-id "$AZURE_CLIENT_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --scope "/subscriptions/$AZURE_SUBSCRIPTION_ID"
```

| | |
| --- | --- |
| Boundary | `roleAssignments/write` is held, but only within the resource group |
| Expected | non-zero, `AuthorizationFailed` |
| If it succeeded | the principal could escalate itself; delete the assignment and treat as a serious failure |

The sharpest of the four. The principal genuinely holds
`Microsoft.Authorization/roleAssignments/write` — the template needs it — so this
probe tests that the *scope* bounds it, not that the operation is absent. A
principal that can assign roles at subscription scope can make itself Owner.

### P4 — an undeclared resource type, inside the declared scope

```bash
az identity create \
  --name id-ai300-denied-probe \
  --resource-group rg-ai300-test01
```

| | |
| --- | --- |
| Boundary | inside the right resource group, outside the permitted operations |
| Expected | non-zero, `AuthorizationFailed` |
| If it succeeded | a user-assigned identity exists; free, delete it, run fails |

This is the axis a general-management built-in role would have left wide open,
and it is what the FR-006 clarification bought. `Microsoft.ManagedIdentity` is
registered on this subscription (R7), so a refusal here is an authorization
refusal and not a provider-registration error.

## Evidence capture

Each probe writes its command and the refusal into the run log, and the captured
output is copied to `specs/003-ci-oidc-deploy/evidence/` with its run id. FR-016
wants the exact command and the exact error, so the log excerpt is stored
verbatim rather than summarised.

## Authentication refusals — not probes, but part of SC-004

These are not assertions in the workflow; they are recorded once during
implementation.

| # | What is attempted | Expected |
| --- | --- | --- |
| A1 | a run on the deploying branch that has not passed the approval gate | refused at authentication; no matching federated identity for that subject |
| A2 | authentication from a context that does not satisfy the trust condition | same class of refusal |
| A3 | `az login --service-principal` from the author's machine, using only the stored identifiers | refused — no credential exists to present |

All three must fail at **authentication**. An authorization error would mean the
context was trusted after all, and would be a finding rather than a pass.
