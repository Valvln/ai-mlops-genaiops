# Implementation Plan: Deployment from continuous integration, without a stored secret

**Branch**: `003-ci-oidc-deploy` | **Date**: 2026-08-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-ci-oidc-deploy/spec.md`

## Summary

Give continuous integration an identity of its own — registered by the author,
trusted only from a gated workflow run, and authorised over exactly one resource
group — then have it deploy `infra/main.bicep` and prove, by four refused
commands, that it can do nothing else.

The technical approach turns on one idea that runs through every artifact:
**observe, do not assume.** The role's operations come from the activity log of a
deployment that already happened, filtered to the caller that actually performed
them. The trust condition's subject comes from a token that was actually issued,
not from the documented format — which for this repository would have been wrong
(R3). The boundary comes from commands that were actually refused, asserted on
every run rather than captured once.

## Technical Context

**Language/Version**: Bicep (CLI `0.46.1`), GitHub Actions workflow YAML, Azure CLI

**Primary Dependencies**: `azure/login@v3.0.1` pinned to SHA `858f4093…`;
`actions/checkout@v4` pinned to SHA `11d5960a…`; Azure CLI preinstalled on
`ubuntu-latest`

**Storage**: N/A — no application data. Objects created live in Entra, GitHub,
and Azure Resource Manager; see [data-model.md](data-model.md)

**Testing**: `az bicep build` for templates; the workflow run itself is the
integration test; four in-workflow assertions for the boundary
([contracts/boundary-probes.md](contracts/boundary-probes.md))

**Target Platform**: Azure subscription `5900fbc9-…`, resource group
`rg-ai300-test01`, `northeurope`; GitHub repository `Valvln/ai-mlops-genaiops`
(public, created 2026-08-05)

**Project Type**: Infrastructure and CI configuration — no application code

**Performance Goals**: N/A

**Constraints**: added cost **0.00**; the deployment must leave the six-resource
inventory identical; the existing validation workflow must keep running with no
credential

**Scale/Scope**: one identity, one custom role, one resource group in scope, two
workflows, ten-or-so permitted operations

## Constitution Check

*GATE: passed before Phase 0. Re-checked after Phase 1 — see foot of section.*

| Principle | Status | How this plan satisfies it |
| --- | --- | --- |
| **I. Cost Discipline** (non-negotiable) | **PASS** | Every object is control-plane metadata or free tier, itemised in [quickstart.md](quickstart.md). Probe targets were chosen so that even an unexpected *success* creates nothing billable (R7) — the cheapest correct option, not merely a cheap one. SC-008 verifies against the cost report rather than by assertion. |
| **II. Version Control Hygiene** | **PASS** | `infra/ci-identity.bicep` is source; no build output is tracked. All API versions resolved against the live provider (R4, R9), none from memory. Action pins resolved from the GitHub API. |
| **III. Commit Authorization** (non-negotiable) | **PASS** | No commit is made by this plan. Task ordering yields one logical change per commit — see Structure Decision. The Spec Kit auto-commit hooks remain `optional: true` and were declined at every step of this feature. |
| **IV. Documentation Ownership** | **PASS** | `README.md` is drafted for the author at the close, not written on his behalf. `infra/DEPLOY.md` gains the identity runbook and the reversal — it is operational documentation, which is Claude's to draft. |
| **V. Validation Before Commit** | **PASS** | `az bicep build` runs on `ci-identity.bicep` before it is proposed; the validation workflow is extended to build **every** template under `infra/`, so this holds for templates added later too. The workflow change itself is validated by a green run, not by inspection. |
| **VI. English Only** | **PASS** | All artifacts in English. |
| **VII. Folder Structure** | **PASS** | Bicep in `infra/`, workflows in `.github/workflows/`, feature artifacts in `specs/003-ci-oidc-deploy/`. No new top-level folder. |

**One thing to flag rather than bury.** Principle V distinguishes *validated to
compile* from *verified to work*. This feature cannot be delivered as
compile-validated only: a workflow that builds is not a workflow that deployed,
and a role definition that compiles proves nothing about whether it authorises
the deployment. Every criterion in the spec is settled by a run, and the plan
budgets for the failed runs that produces (see Discovery below). Nothing here
should be reported as verified before its run exists.

**Post-Phase-1 re-check**: no violation introduced. The design added a probe
resource group (free), a custom role definition (free), and a second workflow
(free on a public repository). No entry in the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/003-ci-oidc-deploy/
├── plan.md                        # This file
├── spec.md
├── research.md                    # Phase 0 — the live findings
├── data-model.md                  # Phase 1 — objects, across three control planes
├── quickstart.md                  # Phase 1 — how each criterion is settled
├── contracts/
│   ├── role-definition.md         # the operation set, with provenance per line
│   ├── boundary-probes.md         # the four commands that must fail
│   └── workflow-contract.md       # triggers, permissions, pins
├── checklists/requirements.md
├── evidence/                      # captured refusals, inventories, run ids
└── tasks.md                       # /speckit-tasks — not created here
```

### Source code (repository root)

```text
.github/workflows/
├── bicep-validate.yml    # existing — extended to build every template under infra/
└── infra-deploy.yml      # new — deploy job + boundary job, gated by an environment

infra/
├── main.bicep            # unchanged — what CI deploys
├── ci-identity.bicep     # new — custom role definition + assignment, author-deployed
└── DEPLOY.md             # revised — identity runbook, CI path, reversal
```

**Structure Decision**: `main.bicep` is left untouched. It is the payload, and
changing it while changing who deploys it would make a failed run ambiguous
between the two. `ci-identity.bicep` is a separate template because the authority
CI runs with cannot be deployed by CI — the split is forced, not stylistic (R8).

Commit boundaries follow the same seams, one logical change each:

1. `infra/ci-identity.bicep` — the role and its assignment
2. `.github/workflows/infra-deploy.yml` — the deploying workflow
3. `.github/workflows/bicep-validate.yml` — the widened build step
4. `infra/DEPLOY.md` — runbook and reversal
5. `specs/003-ci-oidc-deploy/` — evidence and the closing record

## Approach

### Setup, in the order the dependencies force

Detailed in [data-model.md](data-model.md). The order matters because getting it
wrong costs a gate approval per mistake:

1. Application registration and its service principal — **no credential of any
   kind is ever added** (FR-002).
2. GitHub environment `azure-deploy`, required reviewer the author, self-review
   left enabled (R5), deployment branches limited to `main`.
3. Store the three identifiers as repository secrets (R10).
4. **A run that deliberately fails**: request a token, print only its `sub`,
   `aud` and `iss` claims. This yields the real subject *and* SC-004's first
   authentication refusal, in one run.
5. Federated credential, created from the observed subject.
6. `rg-ai300-probe`, empty, so probe P2 has a named target (FR-017b).
7. `ci-identity.bicep` deployed by the author.

### Discovery — the part that is meant to fail

The role ships seeded from the derivation pass: eight operations, each traced to
an activity-log line attributed to the deploying caller
([contracts/role-definition.md](contracts/role-definition.md)). That set is
known-incomplete — the activity log does not record reads.

Verification then runs the workflow and reads what breaks. Each failure names a
missing operation; that operation is added with the run id as its provenance, and
the workflow runs again. Expect **two to four iterations**, each costing a gate
approval.

Two ways to get this wrong, both worth naming in advance:

- **Adding an operation that no failure named.** It would satisfy FR-006 in form
  while abandoning FR-006c. The provenance column is the guard: an empty cell
  means the operation does not ship.
- **Reading a failure that is not about authority.** A queued deployment, a
  transient error, or an unregistered provider can all read like a refusal.
  FR-017 applies here as much as to the probes.

### Proving the boundary

The four probes run as assertions in a second job, on every deployment
([contracts/boundary-probes.md](contracts/boundary-probes.md)). Written as
assertions rather than captures, they convert SC-003 from a one-day observation
into a standing test: widen the role later and a deployment goes red.

The three authentication refusals (SC-004) are recorded once — the first falls
out of setup step 4, before the federated credential exists, which is cheaper
than breaking a working credential later to reproduce it.

### Closing

Withdraw the grant, run, record the failure; restore, run, record the success
(SC-007). Walk the final role against the provenance table and delete anything
unaccounted for. Capture the after-inventory, the cost report, and the credential
enumeration. Write the reversal into `infra/DEPLOY.md`. Draft `README.md` text
for the author to rewrite.

## Risks

| Risk | Handling |
| --- | --- |
| The subject format is wrong and the failure reads like a typo | Setup step 4 reads the subject from an issued token instead of constructing it (R3). This is the single most likely way to lose a session. |
| The activity log is taken unfiltered and over-grants | Provenance is per-caller; three operations were excluded on exactly this basis (R2). |
| A probe fails for the wrong reason and passes as evidence | Assertions check the error class, not just the exit code. `Microsoft.Network` was rejected as a probe target for being unregistered (R7). |
| Discovery iterations exhaust patience and a built-in role gets substituted | That is the FR-006 clarification reversed without saying so. The seeded eight operations should make the first run close. |
| Gate approvals slow the loop | Accepted deliberately; `workflow_dispatch` exists so iterations do not need commits (FR-014a). |
| The 90-day vault name hold | Not touched — this feature never deletes the environment. |

## Complexity Tracking

No constitutional violation requires justification. Table intentionally empty.
