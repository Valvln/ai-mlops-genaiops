# Phase 0 Research: Azure ML Workspace

**Feature**: [spec.md](./spec.md) | **Date**: 2026-08-06

All findings below were produced by querying the live Azure provider and by
compiling a throwaway probe template locally. Nothing here is recalled from
memory or copied from an example of unknown age, per constitution principle II.

## R1 — API version for `Microsoft.MachineLearningServices/workspaces`

**Command**:

```bash
az provider show --namespace Microsoft.MachineLearningServices \
  --query "resourceTypes[?resourceType=='workspaces'].apiVersions[]"
```

**Findings**: the newest generally-available version is `2026-05-01`. The
version named in the original feature request, `2024-10-01`, is still listed and
therefore still supported, but is six GA releases behind. Preview versions
(`2026-05-15-preview`, `2026-03-15-preview`, …) exist and are excluded on
principle.

**Decision**: `2026-05-01`.

**Rationale**: current, generally available, and — verified in R4 — fully
type-checked by the installed Bicep CLI, so property errors surface locally
instead of at deployment.

**Alternatives considered**: `2024-10-01` (as originally requested) — still
valid, but choosing a stale version without cause is exactly what principle II
exists to prevent. Preview versions — rejected outright; a learning environment
gains nothing from an unstable contract.

## R2 — API version for `Microsoft.Insights/components`

**Command**:

```bash
az provider show --namespace Microsoft.Insights \
  --query "resourceTypes[?resourceType=='components'].apiVersions[]"
```

**Findings**: the newest generally-available version is `2020-02-02`. This is
not neglect — it is the version that introduced workspace-based Application
Insights, and the schema has been stable since. The older `2015-05-01`
corresponds to the classic, now-retired model.

**Decision**: `2020-02-02`, with `WorkspaceResourceId` pointing at the Log
Analytics workspace and `IngestionMode: 'LogAnalytics'`.

**Rationale**: classic Application Insights is retired. A component declared
without `WorkspaceResourceId` would compile locally but be rejected at
deployment — the concrete reason the log workspace entered scope as decision D1
in the spec.

**Alternatives considered**: `2015-05-01` classic — rejected, retired.

## R3 — API version for `Microsoft.OperationalInsights/workspaces` (the trade-off)

**Commands**: `az provider show --namespace Microsoft.OperationalInsights …`,
then a per-version compile probe.

**Findings**: the provider advertises `2026-03-01` as the newest GA version. The
installed Bicep CLI does **not** ship type definitions for it:

```text
Warning BCP081: Resource type "Microsoft.OperationalInsights/workspaces@2026-03-01"
does not have types available. Bicep is unable to validate resource properties
prior to deployment, but this will not block the resource from being deployed.
```

Probe results across candidate versions:

| Version      | Bicep type-checking          |
| ------------ | ---------------------------- |
| `2026-03-01` | none — BCP081                |
| `2025-07-01` | full                         |
| `2025-02-01` | full                         |
| `2023-09-01` | full                         |

`az bicep list-versions` confirms the installed CLI (**0.46.1**) is already the
newest release, so this is not a stale-tooling problem that upgrading would fix:
the provider has simply moved ahead of the Bicep type catalogue.

**Decision**: `2025-07-01` — the newest GA version the toolchain can actually
validate.

**Rationale**: this is the one place where "newest GA" and "locally verifiable"
genuinely conflict, so it is recorded rather than silently resolved. Principle V
requires validation before commit, and BCP081 would mean this resource's
properties are *not* validated — a typo in `retentionInDays` would compile
cleanly and fail only on deployment. Taking a version eight months older buys
real local type-checking. Log Analytics workspace schema is stable across this
range; nothing this feature uses (`sku.name`, `retentionInDays`) differs between
the two.

**Alternatives considered**:

- `2026-03-01` with the BCP081 warning accepted — rejected. It would leave a
  permanent warning in every build and hollow out the validation gate for one of
  the four new resources.
- Suppressing BCP081 with `#disable-next-line` — rejected as worse: it hides the
  warning without restoring any of the checking that was lost.

**Revisit when**: a future Bicep CLI ships types for `2026-03-01`. Re-run the
probe then and move up.

## R4 — Workspace schema verification under `2026-05-01`

**Method**: a probe template in a scratch directory declaring all five resources
and compiled with `az bicep build`. Exit code 0, with BCP081 on the Log
Analytics line as the only diagnostic — confirming that everything else,
including the whole ML workspace declaration, was type-checked and accepted.

**Confirmed**:

- `identity: { type: 'SystemAssigned' }` — accepted.
- `sku: { name: 'Basic', tier: 'Basic' }` — accepted.
- `properties.storageAccount`, `properties.keyVault`,
  `properties.applicationInsights` — all accepted as resource-id strings; these
  property names did not change between `2024-10-01` and `2026-05-01`.
- `properties.containerRegistry` — optional. Omitting it compiles cleanly; no
  placeholder or explicit `null` is needed, which satisfies FR-007 in the most
  literal way available.

**Note carried to deployment (out of scope here)**: newer workspace API versions
expose `managedNetwork`. It is left unset, which means the service default
applies. Since this feature never deploys, that default is not exercised — but
it should be confirmed before any future deployment, as managed network
isolation can carry cost.

## R5 — Name generation

`uniqueString(resourceGroup().id)` yields 13 characters. With the `ai300ml`
prefix the workspace name is 20 characters, inside the 3–33 character limit for
the resource type, and consistent with how `storageAccountName` and
`keyVaultName` are already derived in the template. The same pattern extends to
the two telemetry resources.

## Summary of versions to use

| Resource                                          | API version  | Status                            |
| ------------------------------------------------- | ------------ | --------------------------------- |
| `Microsoft.OperationalInsights/workspaces`        | `2025-07-01` | newest **type-checkable** GA (R3) |
| `Microsoft.Insights/components`                   | `2020-02-02` | newest GA                         |
| `Microsoft.MachineLearningServices/workspaces`    | `2026-05-01` | newest GA                         |

Existing resources are left untouched at their current versions
(`Microsoft.Storage/storageAccounts@2023-01-01`,
`Microsoft.KeyVault/vaults@2025-05-01`).
