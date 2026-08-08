# Implementation Plan: Least-privilege permissions for the workspace identity

> **Superseded in part, 2026-08-08.** The approach below was attempted and
> failed: the platform maintains this identity's permissions and recreates what
> is deleted. The design is kept as the record of what was tried and why. See
> [research.md](research.md) R10 and the Outcome section of [spec.md](spec.md).


**Branch**: `002-workspace-identity-least-privilege` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-workspace-identity-least-privilege/spec.md`

## Summary

Take the workspace's managed identity from four platform-granted permissions —
one of them authority over the whole resource group — down to **two**, both
declared in `infra/main.bicep` and both scoped to a single resource.

The approach follows from what the live environment turned out to look like.
Because the workspace's four default datastores are **identity-based** (no
stored credentials), blob data access is load-bearing and stays. Because nothing
mounts a file share without a compute target, file access goes. Because
governing who may read the vault is forbidden by FR-005, vault administration is
replaced by the narrowest secret role the evidence supports.

Ownership transfers by replacement, not by addition: the platform's grants
cannot be re-declared under a template-derived name, so each one is removed and
the template creates its own. The ordering is chosen so exactly one permission
gap opens, for the length of one deployment.

## Technical Context

**Language/Version**: Bicep, compiled by Azure CLI 2.89.0

**Primary Dependencies**: `Microsoft.Authorization/roleAssignments@2022-04-01` — the latest **generally available** version on the live provider; everything newer is preview and excluded by constitution principle II (research.md R1)

**Storage**: N/A — this feature declares no data of its own

**Testing**: `az bicep build` for compilation; `az deployment group what-if` for the dry run; `az role assignment list` for the effective result; `az ml workspace diagnose` as a service-side probe with a mandatory negative control (research.md R4)

**Target Platform**: Azure resource group `rg-ai300-test01`, `northeurope`, live since 2026-08-07

**Project Type**: Infrastructure as code — a single template, extended in place

**Performance Goals**: N/A

**Constraints**: added recurring cost **$0**; no new resource; no change to the five deployed resources; no secret; no principal other than the workspace identity

**Scale/Scope**: two declared role assignments, four platform grants removed, one template file touched, one runbook section added

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 — result below.*

| Principle | Assessment | Status |
| --- | --- | --- |
| **I — Cost discipline** | Role assignments are control-plane metadata and are not billed. No resource is created and no tier changes. Added recurring cost is **$0**, stated before implementation as required. The `az ml` extension is a free local install. No compute or endpoint is provisioned, so nothing can be left running. | **PASS** |
| **II — Version control hygiene** | Only `infra/main.bicep` is tracked; `infra/main.json` remains a build output and stays gitignored. The API version was resolved against the live provider and the latest GA was chosen over the newer previews. Role identifiers were resolved live rather than transcribed from an example. | **PASS** |
| **III — Commit authorization** | Every commit is proposed to the author with a diff. `auto_commit.default` remains `false` and no auto-commit hook is executed. Removing a grant is a live-environment act and is proposed for authorization separately from the template change (FR-013). | **PASS** |
| **IV — Documentation ownership** | The runbook gains a permissions section and a reversal. `README.md` text is drafted for the author to rewrite, not written as a changelog. | **PASS** |
| **V — Validation before commit** | `az bicep build` and `what-if` run before the template change is proposed. The post-deployment check is separate and reported separately. Anything unverified is reported as unverified — see the two items under Honest status below. | **PASS** |
| **VI — English only** | All artifacts in English. | **PASS** |
| **VII — Folder structure** | Changes land in `infra/`, which is where infrastructure lives. No new top-level folder. | **PASS** |

**Gate result: PASS**, with no violations to justify. The Complexity Tracking
table is therefore omitted.

### Honest status of two claims

Principle V draws a line between *validated to compile* and *verified to work*.
Two things this plan relies on sit on the wrong side of it, and are recorded
rather than presented as settled:

1. **The duplicate-grant rejection is reasoned, not observed.** That the
   platform refuses an identical identity/role/scope combination under a
   different name is well-established behaviour and is why the ordering deletes
   before it declares — but it has not been seen on this subscription. The
   ordering is arranged so the claim never needs a destructive test.
2. **The service-side probe's sensitivity is unproven.** `az ml workspace
   diagnose` runs and returns a clean baseline. Whether it detects a *missing
   role assignment* — as opposed to a network or lock problem — is unknown. The
   negative control in the quickstart exists to settle it, and if it turns out
   the probe is insensitive, SC-006 is reported unverified rather than passed on
   an empty result that means nothing.

## Project Structure

### Documentation (this feature)

```text
specs/002-workspace-identity-least-privilege/
├── plan.md                        # This file
├── spec.md                        # What and why, with four clarifications
├── research.md                    # Phase 0 — nine findings, all from the live subscription
├── data-model.md                  # Phase 1 — current state, target state, transition, ordering
├── quickstart.md                  # Phase 1 — the validation sequence
├── contracts/
│   └── role-assignments.md        # Phase 1 — exact declarations, removals, reversal
├── checklists/
│   └── requirements.md            # Spec quality checklist
└── tasks.md                       # Phase 2 — NOT created by /speckit-plan
```

### Source code (repository root)

```text
infra/
├── main.bicep    # MODIFIED — two role assignments and two role-id variables appended
├── main.json     # build output, gitignored, regenerated by az bicep build
└── DEPLOY.md     # MODIFIED — new section: what the identity may do, and how to put it back
```

**Structure Decision**: the two assignments are declared in `infra/main.bicep`
itself rather than in a separate module. The repository has a single template
and the constitution favours one reviewable source file; a module would add
indirection for two resources and would separate a permission from the resource
it applies to, which is the thing a reviewer most needs to see together.

## Design decisions, and what drove each

| Decision | Driven by |
| --- | --- |
| Keep blob data access | The four default datastores carry no credentials — access is authorised as the identity, so this is the only path to the workspace's own artifacts (research.md R3) |
| Drop file share access | Only a compute target mounts a file share, and there is none. **This is the riskiest removal**: the two file datastores exist today, so this is "unused", not "unreferenced" |
| Replace vault administration with secret **read** | Administration confers governing who else may access, which FR-005 forbids. Read is the narrower of the two candidates and the only one supported by an observed fact — no credential-carrying datastore or connection exists (research.md R6) |
| Grant nothing on the telemetry resources | Telemetry comes from jobs and endpoints; there are none (research.md R7) |
| Delete before declaring, per grant | The platform's random assignment names cannot be reproduced by a template (research.md R8) |
| Create the vault grant before deleting the old one | The two role definitions differ, so both may coexist — which means the vault gap can be avoided entirely |
| `principalType: 'ServicePrincipal'` | Avoids a directory-replication failure on a clean rebuild, where the identity is minutes old (research.md R9) |

## The vault permission — decided, with its uncertainty carried forward

**Decided by the author on 2026-08-07: secret read** (Key Vault Secrets User).

The basis is an observed fact — no credential-carrying datastore or connection
exists, so there is nothing for the workspace to write — plus the inference that
a workspace with nothing to write does not need write access. **The inference is
unverified**, and could not be verified: Owner grants no data-plane access under
RBAC, so the vault's contents cannot be listed (research.md R5), and settling it
that way would mean granting the author a vault data role, which FR-011 places
outside this feature.

The decision was therefore taken deliberately on incomplete evidence rather than
deferred. If read turns out to be too narrow, the symptom is an authorization
error, and the fix is to widen to secret write — **not** to restore vault
administration, which confers control over who else may access the vault and is
what FR-005 exists to forbid.

## Phase status

- **Phase 0 — Research**: complete. Nine findings in [research.md](research.md),
  all obtained by querying the live subscription. One item (R6) is explicitly
  left open with a proposal rather than closed by a guess.
- **Phase 1 — Design & contracts**: complete.
  [data-model.md](data-model.md), [contracts/role-assignments.md](contracts/role-assignments.md),
  [quickstart.md](quickstart.md).
- **Phase 2 — Tasks**: not started. `/speckit-tasks` generates it.
