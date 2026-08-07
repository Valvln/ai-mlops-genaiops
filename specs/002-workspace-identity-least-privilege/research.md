# Phase 0 — Research

Every finding below was obtained by querying the live subscription on
2026-08-07. Nothing here is recalled from memory or copied from an example.
Where something could not be established, it says so.

All commands used were reads. No resource was created, modified, or deleted
during this phase. Cost incurred: zero.

---

## R1 — API version for role assignments

**Decision**: `Microsoft.Authorization/roleAssignments@2022-04-01`.

**Rationale**: the live provider lists twenty versions. Everything newer than
`2022-04-01` is a preview (`2026-07-01-preview`, `2025-10-01-preview`), and
constitution principle II requires the latest **generally available** version,
never a preview. `2022-04-01` is therefore both the newest GA version and the
current one.

```bash
az provider show --namespace Microsoft.Authorization \
  --query "resourceTypes[?resourceType=='roleAssignments'].apiVersions[]" -o tsv
```

**Alternatives considered**: `2026-07-01-preview` was rejected on the principle
alone. `2020-04-01-preview` is what many published examples still use and was
rejected as both stale and preview.

---

## R2 — Role definition identifiers

Resolved against the live tenant rather than transcribed. These are the
stable, tenant-independent identifiers of the built-in definitions.

| Role | Identifier |
| --- | --- |
| Storage Blob Data Contributor | `ba92f5b4-2d11-453d-a403-e96b0029c9fe` |
| Storage Blob Data Reader | `2a2b9908-6ea1-4ae2-8e65-a410df84e7d1` |
| Storage File Data Privileged Contributor | `69566ab7-960f-475b-8e7c-b3118f30c6bd` |
| Key Vault Secrets User | `4633458b-17de-408a-b874-0445c86b69e6` |
| Key Vault Secrets Officer | `b86a8fe4-44ce-4948-aee5-eccb2c155cd7` |
| Key Vault Administrator | `00482a5a-887f-4fb3-b363-3b7fe8e74483` |
| Monitoring Metrics Publisher | `3913510d-42f4-4e42-8a64-420c390055eb` |

---

## R3 — The default datastores are identity-based, and two of them are file shares

This is the finding that most affects the reduction, and it was not visible
from the template.

The workspace created four datastores of its own accord:

| Datastore | Type | Stored credential |
| --- | --- | --- |
| `workspaceblobstore` | blob | none |
| `workspaceartifactstore` | blob | none |
| `workspacefilestore` | **file share** | none |
| `workspaceworkingdirectory` | **file share** | none |

**All four carry `credentials: {}`** — they are identity-based. Nothing reaches
this storage with a stored key; access is authorised as the workspace identity.

Two consequences:

1. **The blob permission is genuinely load-bearing.** With identity-based
   datastores, removing the identity's blob data access removes the only way the
   service can read or write the workspace's own artifacts. This is not a
   permission held "just in case".
2. **The file permission is riskier to drop than the spec assumed.** The
   specification treated file-share access as backing a capability "not built
   yet". That is half right: the two file datastores **exist today**, created by
   the workspace itself. What does not exist is anything that mounts them — a
   file share is mounted by a compute target, and there is no compute. So the
   permission is unused today but not unreferenced, which is a weaker position
   than the spec's wording implies.

**Decision**: drop the file permission anyway, per the clarification recorded in
the spec. Record explicitly in the runbook that the two file datastores become
unusable by the service until it is re-granted, and that this is the accepted
cost rather than an oversight. This is the single largest risk the plan carries.

---

## R4 — What can act as the service's own identity, without compute

FR-004a requires evidence produced by the service acting as itself, plus a
negative control. Two candidate instruments exist in the tooling, and neither
was known to work before it was run.

### `az ml workspace diagnose` — usable, sensitivity unproven

Runs server-side and reports per-dependency findings. Baseline captured before
any change:

```json
{
  "applicationInsightsResults": [], "containerRegistryResults": [],
  "dnsResolutionResults": [], "keyVaultResults": [],
  "networkSecurityRuleResults": [], "otherResults": [],
  "resourceLockResults": [], "storageAccountResults": [],
  "userDefinedRouteResults": []
}
```

All arrays empty — the workspace reports no problem with any dependency.

**What this establishes**: a baseline, and that the command runs. **What it does
not establish**: that `diagnose` is sensitive to a missing role assignment at
all. It may only test network reachability, DNS, and resource locks. An empty
result after the reduction would then be worthless as evidence.

**Decision**: use `diagnose` as one probe, but treat its sensitivity as
**unproven until the negative control demonstrates it**. If withholding a
permission does not make `diagnose` report anything, `diagnose` is disqualified
as evidence for that permission and the plan must say so rather than quote an
empty result as a pass. This is exactly the failure mode FR-004a exists to
prevent.

### `az ml workspace sync-keys` — a probe for control-plane access

Makes the service fetch keys from its dependent resources. It is the operation
most likely to need `listKeys` on the storage account, which is a **control
plane** action and is *not* included in blob data access — it was covered only
by the resource-group-wide grant being removed.

**Decision**: run it as a probe, but classify its failure carefully. `sync-keys`
is a maintenance operation with no current consumer in this project, so under
FR-004 its failure is **not** by itself proof that a needed permission was lost.
It is recorded as a finding for the author, not treated as an automatic trigger
for FR-016 restoration. Distinguishing the two is the point: FR-016 restores
when something the environment *does* breaks, not when something it *could* do
stops being possible.

---

## R5 — Owner does not confer Key Vault data-plane access

Attempting to list the vault's secrets as the signed-in Owner fails:

```text
(Forbidden) Caller is not authorized to perform action on resource.
Action: 'Microsoft.KeyVault/vaults/secrets/readMetadata/action'
Assignment: (not found)
```

**What this confirms**: the vault is genuinely enforcing RBAC, and the
management-plane Owner role grants nothing on the data plane. Worth knowing on
its own — it is a common exam trap and a common real-world surprise.

**What it costs this feature**: the contents of the vault cannot be enumerated,
so it cannot be established by observation whether the workspace has written
secrets there. See the open question in R6.

**Not done deliberately**: granting the author a vault data role would answer it,
but FR-011 forbids this feature from granting permissions to any principal other
than the workspace identity. The question is left open for the author rather
than resolved by quietly stepping outside the feature's scope.

---

## R6 — The one undecided permission: what the identity needs on the vault

**Status: OPEN — the plan proposes a choice and a way to settle it, but does not
claim to have settled it.**

The current grant (Key Vault Administrator) is disqualified outright: it confers
control over who else may access the vault, which FR-005 forbids. The
replacement is a choice between two:

| Candidate | Confers | Fits FR-004 if… |
| --- | --- | --- |
| Key Vault Secrets User | read secrets | the workspace only reads secrets it already has |
| Key Vault Secrets Officer | read **and write** secrets | the workspace also writes secrets today |

Azure ML writes secrets to the vault when a credential-carrying datastore or
connection is created. **This workspace has neither** — R3 showed all four
datastores are identity-based and carry no credentials. That argues for read
only.

Against that: it cannot be observed (R5) whether the workspace wrote anything to
the vault during creation, and if it did, it will likely need to write again.

**Proposed decision**: **Key Vault Secrets User** — the narrower of the two —
because it is the only one of the pair supported by an observed fact, and the
clarification in the spec settled that an unproven future need does not justify
a permission. The cost if wrong is an authorization failure, which FR-016 turns
into a recorded finding and a one-command restore.

**How to settle it properly**: the author grants himself vault read access
temporarily and lists the secrets. That is a decision for the author, not
something this plan performs — it grants a permission to a principal the feature
declares out of scope.

---

## R7 — Nothing is granted on the telemetry resources

**Decision**: grant the identity no permission on Application Insights or the
Log Analytics workspace.

**Rationale**: telemetry reaches those resources from jobs and endpoints. There
are none, and none is in scope. Under FR-004 a permission with no current
consumer is not granted. Monitoring Metrics Publisher is the role that would be
needed and is deliberately not used.

**Consequence to expect**: when the first job runs, this is a plausible place for
an authorization failure to appear. Recorded in the runbook so it is recognised
rather than diagnosed.

---

## R8 — Naming, and why the platform's grants cannot simply be adopted

**Decision**: name each declared assignment
`guid(<scope resource id>, <workspace resource id>, <role definition id>)`.

**Rationale**: the name of a role assignment must be a GUID and must be unique
within its scope. Deriving it from the three things that define the assignment
makes redeployment idempotent — the same inputs produce the same name, so the
platform sees the same resource rather than a second one. This is what SC-008
tests.

**Why the existing grants cannot be re-declared as they stand**: the platform
created them with random names (for example `d37b8682-…` at resource-group
scope). A template cannot reproduce a random name, and requesting the same
identity/role/scope combination under a *different* name is rejected as a
duplicate.

**Verification status**: this rejection is well-established platform behaviour
and is the reason for the delete-then-declare ordering, **but it has not been
observed on this subscription**. It is reasoned, not verified. The ordering in
this plan is designed so the claim never has to be tested destructively — but if
it turns out to be wrong, the only consequence is that a step was unnecessary.

---

## R9 — `principalType` must be set

**Decision**: set `principalType: 'ServicePrincipal'` on every declared
assignment.

**Rationale**: without it, the platform validates the principal by looking it up
in the directory, and a newly created identity may not have replicated yet,
producing an intermittent `PrincipalNotFound` at deployment. Declaring the type
skips that lookup. The workspace identity already exists here, so the failure is
unlikely today — but the template must also work on a clean rebuild, where the
identity is minutes old.

---

## Summary of decisions

| # | Decision | Basis |
| --- | --- | --- |
| R1 | API version `2022-04-01` | latest GA on the live provider |
| R2 | Role identifiers as listed | resolved live |
| R3 | Blob access kept; file access dropped | datastores observed identity-based |
| R4 | `diagnose` + `sync-keys` as probes, sensitivity to be proven | run against the live workspace |
| R5 | Vault contents cannot be inspected | observed Forbidden as Owner |
| R6 | Key Vault Secrets User — **proposed, not settled** | narrower of two; only one supported by evidence |
| R7 | No telemetry permissions | no current consumer |
| R8 | Deterministic `guid()` naming; delete before declare | idempotence requirement |
| R9 | `principalType` declared | avoids replication-delay failures |
