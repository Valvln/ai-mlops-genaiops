# Implementation Plan: Azure ML Workspace in the shared infrastructure template

**Branch**: `001-azure-ml-workspace` | **Date**: 2026-08-06 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-azure-ml-workspace/spec.md`

## Summary

Extend the single existing Bicep template with a machine learning workspace that
reuses the storage account and key vault already declared there, backed by a new
Application Insights component and the Log Analytics workspace that component
requires. The workspace carries a system-assigned managed identity, sits on the
Basic SKU, and is deliberately left without a container registry or any compute.

The whole feature is template authoring plus local validation. No deployment is
performed, so every success criterion is checked by compiling the template and
inspecting the compiled output.

## Technical Context

**Language/Version**: Bicep, compiled with Bicep CLI 0.46.1 (verified as the
newest release)

**Primary Dependencies**: Azure CLI (`az bicep build`); Azure Resource Manager
providers `Microsoft.MachineLearningServices`, `Microsoft.Insights`,
`Microsoft.OperationalInsights`

**Storage**: N/A — the feature declares infrastructure, it does not persist
application data

**Testing**: `az bicep build` for compilation, plus assertions against the
compiled ARM JSON (resource count, absence of `containerRegistry`, absence of
literal subscription/tenant values, presence of outputs). See
[quickstart.md](./quickstart.md).

**Target Platform**: Azure Resource Manager, resource-group scope, region
`westeurope` (existing template default)

**Project Type**: Infrastructure as code — single template file, no application
source

**Performance Goals**: N/A

**Constraints**: $0 added recurring cost; no deployment; no hardcoded
subscription, tenant, or resource-group identifiers; no preview API versions

**Scale/Scope**: One resource group, one learning environment, +3 resources on
top of the existing 2

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Initial | Post-design |
| --- | --- | --- | --- |
| I. Cost Discipline | Cheapest suitable SKUs; cost flagged before implementation; nothing left running | PASS | PASS |
| II. Version Control Hygiene | API versions verified against the live provider; no generated artifact tracked | PASS | PASS |
| III. Commit Authorization | No automatic commit; author reviews a diff first | PASS | PASS |
| IV. Documentation Ownership | README updated at the milestone, first person, authored by the project owner | DEFERRED | DEFERRED |
| V. Validation Before Commit | `az bicep build` green before anything is proposed for commit | PASS | PASS |
| VI. English Only | All artifacts in English | PASS | PASS |
| VII. Folder Structure | Infrastructure change lands in `infra/` | PASS | PASS |

**Notes on the gates**

- **I** — Added recurring cost is **$0**. Basic is the entry SKU for the
  workspace; Application Insights and Log Analytics are consumption-billed with
  a free monthly allowance far above this project's volume; no compute and no
  container registry are declared. Nothing is deployed, so nothing can be left
  running.
- **II** — Every API version is justified in [research.md](./research.md),
  including the one place (R3) where the newest GA version was deliberately
  *not* taken. `infra/main.json` is already gitignored and stays that way.
- **III** — The `speckit.git.commit` hooks the git extension registers are all
  `optional: true`, and `git-config.yml` ships with auto-commit disabled
  (`auto_commit.default` is `false`). No commit happens without the author.
- **IV** — Deferred by design, not skipped: `README.md` is the author's
  first-person account, so Claude may draft candidate text but the author writes
  and commits it. Tracked as the final task.
- **V** — The build gate runs before any commit is proposed. Note that a green
  build proves the template *compiles*, not that it *deploys*; the plan states
  this limit rather than overselling it.

**Result**: no violations. Complexity Tracking is therefore omitted.

## Project Structure

### Documentation (this feature)

```text
specs/001-azure-ml-workspace/
├── spec.md                        # Feature specification (complete)
├── plan.md                        # This file
├── research.md                    # Phase 0 — API version verification and trade-offs
├── data-model.md                  # Phase 1 — resource graph and properties
├── quickstart.md                  # Phase 1 — how to validate the change locally
├── contracts/
│   └── template-interface.md      # Phase 1 — parameters and outputs contract
├── checklists/
│   └── requirements.md            # Spec quality checklist (passing)
└── tasks.md                       # Phase 2 — created by /speckit-tasks, not by this command
```

### Source Code (repository root)

```text
infra/
├── main.bicep                     # THE only file this feature modifies
└── main.json                      # Build output — gitignored, never committed
```

**Structure Decision**: this feature touches exactly one source file,
`infra/main.bicep`. The project deliberately keeps a single template rather than
splitting into modules: at five resources, a module structure would add
indirection without removing any duplication, and the template is meant to be
read end-to-end as a learning artifact. Revisit if the template outgrows roughly
ten resources.

## Implementation Approach

Additive only. Nothing already in the template is modified — the existing
storage account, key vault, and their two outputs stay exactly as they are. The
change appends:

1. **One parameter** — `workspaceName`, defaulting to
   `'ai300ml${uniqueString(resourceGroup().id)}'`, matching the pattern the two
   existing name parameters already use.
2. **Three resources**, in dependency order — Log Analytics workspace,
   Application Insights (referencing it), machine learning workspace
   (referencing storage, key vault, and Application Insights). All references
   use symbolic `.id`, so ARM infers `dependsOn` and no explicit ordering is
   written by hand.
3. **Two outputs** — workspace name and workspace resource id, appended after
   the existing two.

Every new resource carries the same `project: 'ai300-prep'` / `environment:
'learning'` tag pair the existing resources use.

The names of the two telemetry resources are derived inline from
`uniqueString(resourceGroup().id)` rather than promoted to parameters. They are
implementation detail of the workspace's logging, and the spec asks for a
configurable name only for the workspace itself (FR-002).

## Validation Strategy

Success criteria map to concrete, offline checks — full commands in
[quickstart.md](./quickstart.md):

| Criterion | How it is checked |
| --- | --- |
| SC-001 build clean | `az bicep build --file infra/main.bicep`, exit 0, no warnings |
| SC-002 exactly 5 resources | count `.resources` in the compiled JSON |
| SC-003 no container registry | grep the compiled JSON for `containerRegistry` — expect no match |
| SC-004 no literal ids | grep the compiled JSON for subscription/tenant GUID patterns — expect no match |
| SC-005 outputs present | inspect `.outputs` in the compiled JSON |
| SC-006 $0 cost | review of declared SKUs and tiers; no deployment needed to establish it |
| SC-007 offline | satisfied by construction — every check above runs locally |

**Honest limit of this gate**: `az bicep build` is a compile step. It proves the
template is syntactically valid and type-correct against the Bicep type
catalogue. It does **not** prove the template deploys — resource name
collisions, policy denials, quota, and region availability are all invisible to
it. Per principle V the change will be reported as *validated to compile*, never
as *verified to work*.

## Phase 2 Preview

Not executed by this command. `/speckit-tasks` will break the above into ordered
tasks, expected to be roughly: add parameter → add Log Analytics → add
Application Insights → add ML workspace → add outputs → build and assert each
success criterion → draft README text for the author.
