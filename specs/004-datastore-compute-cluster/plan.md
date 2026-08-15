# Implementation Plan: A place to read data from, and a target to run on

**Branch**: `004-datastore-compute-cluster` | **Date**: 2026-08-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-datastore-compute-cluster/spec.md`

## Summary

Add three declared objects to `infra/main.bicep` — a blob container, a
credential-less datastore pointing at it, and an AmlCompute cluster resting at
zero nodes — plus one role assignment that lets the cluster's own identity read
the container. Deploy through the existing approval gate, discovering the
missing CI operations by failing rather than by predicting. Then prove the pair
works with a job that reads a known file and emits its checksum, and prove the
cluster returns to zero afterwards by reading the live resource.

The technical shape is settled in [research.md](./research.md). Two of its
findings drove the design and are worth restating here, because neither was
visible from the specification:

- **The author holds `Owner` and no blob data role**, so a read performed as the
  author's identity would fail. That turns FR-018's claim from an assertion into
  something provable: a job that reads the file successfully has read it as some
  other identity.
- **The workspace identity already holds `Storage Blob Data Contributor` at
  storage-account scope**, which covers the new container. So the role
  assignment this plan adds could be entirely inert — the exact failure feature
  002 shipped. A necessity test is therefore part of the plan, not an optional
  extra.

## Technical Context

**Language/Version**: Bicep (via `az bicep`, current CLI), Azure CLI `ml`
extension v2, Python 3 for the verification job's script

**Primary Dependencies**: The deployment of features 001–003 — resource group
`rg-ai300-test01`, the workspace, its storage account, and the gated
`infra-deploy.yml` workflow with the custom `AI300 CI Deployer` role

**Storage**: A new blob container on the existing storage account. No new
storage account.

**Testing**: `az bicep build` (compiles), `az deployment group what-if`
(deployability), a gated CI deployment (authority), and a job on the cluster
(the pair actually works). Each answers a different question and none
substitutes for another.

**Target Platform**: Azure, `northeurope`

**Project Type**: Infrastructure as code plus a minimal job asset

**Performance Goals**: None. The verification job is deliberately trivial.

**Constraints**: Zero cost at rest, verified after deployment; under 1 € total;
CI role extended only by operations a failure names; the approval gate passed by
the author.

**Scale/Scope**: Three declared resources, one role assignment, one job.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | Evidence |
| --- | --- | --- |
| **I. Cost discipline** (non-negotiable) | **Pass, with a declared first** | This is the first hourly resource in the project and the spec says so up front. Cheapest allocatable SKU chosen against quota, not price alone (R3). Zero at rest is a requirement with a post-deploy check, not a hope. Estimated total well under 1 €. One cost is explicitly unknown and scheduled for measurement rather than assumed away (R8). |
| **II. Version control hygiene** | Pass | API versions read from the live provider manifest on 2026-08-15, not recalled (R1). `infra/*.json` remain untracked build outputs. |
| **III. Commit authorization** (non-negotiable) | Pass | No commit is made by this plan. Auto-commit hooks remain `optional: true` with `auto_commit.default: false`, untouched. Diffs are shown and the author runs the commands. |
| **IV. Documentation ownership** | Pass | `README.md` gets drafted candidate text at the milestone; the author rewrites and commits it. `infra/DEPLOY.md` is revised with observed values, which is its established role. |
| **V. Validation before commit** | Pass | `az bicep build` before any commit is proposed; `what-if` before any deployment. The distinction between *compiles*, *deploys*, and *works* is preserved throughout — see the four-gate table under Phase 2. |
| **VI. English only** | Pass | All artifacts in English. |
| **VII. Folder structure** | Pass | Template changes in `infra/`; the verification job in `mlops/`, which is the existing folder for classical ML operationalization. No new top-level folder. |

**No violations.** The Complexity Tracking table is therefore omitted.

One item deserves naming rather than burying: the plan adds a **role assignment**
that may turn out to do nothing. That is not a constitution violation, but it is
the specific mistake this repository has already made once, so D7's necessity
test is treated as required work rather than as a nice-to-have.

### A refinement of the spec's wording, surfaced rather than absorbed

The spec says the read must happen "using the workspace's own identity rather
than a storage account key". The design uses the **compute cluster's**
system-assigned identity, which is a different principal from the workspace's.

This is a refinement of the wording, not a departure from the intent. The
clarification behind FR-018 rejected the author's credentials on the grounds
that they are "the wrong ones" and that "only a job reads as the identity whose
access is being asserted". The compute identity is the identity the
documentation names for exactly this scenario (R4), and it is the one this
repository can actually scope and test. The claim the feature ends up making is
therefore *the Azure ML side can read this data, as a principal that is not the
author* — which is what the exit criterion was reaching for.

Flagged here so the author can reject it. If the intent really was the workspace
MSI specifically, the design changes: no compute identity, no container grant,
and the reader becomes whichever principal the service picks — at the cost of
the ambiguity R4 describes.

## Project Structure

### Documentation (this feature)

```text
specs/004-datastore-compute-cluster/
├── spec.md              # Phase -1: what and why
├── plan.md              # This file
├── research.md          # Phase 0: the evidence behind every decision
├── data-model.md        # Phase 1: the objects and their properties
├── quickstart.md        # Phase 1: the runnable verification sequence
├── contracts/
│   └── role-additions.md   # Phase 1: the CI role provenance record for this feature
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2, created by /speckit-tasks
```

### Source code (repository root)

```text
infra/
├── main.bicep           # MODIFIED: + container, datastore, cluster, role assignment
├── ci-identity.bicep    # MODIFIED, reactively: one operation per named failure
└── DEPLOY.md            # MODIFIED: observed values, the two findings, shutdown

mlops/
└── datastore-check/     # NEW
    ├── check_datastore.py   # reads the mounted file, prints size + sha256
    ├── job.yml              # the job: command, environment, compute, input
    └── sample.csv           # the known file, with a recorded checksum
```

**Structure Decision**: The template stays a single `main.bicep`. Splitting the
compute into its own file would give CI two deployments to run and two failure
surfaces to read, for a template that is still under 250 lines. The verification
job goes in `mlops/`, matching the constitution's folder table, and is the first
content that folder has held.

## Phase 2 approach — the order, and who runs what

Not tasks (those are `/speckit-tasks`), but the sequence the tasks must respect,
because several steps are only *available* at a particular point.

### Four gates, four different questions

The distinction that has already cost this project two latent defects:

| Gate | Question it answers | What it cannot tell you |
| --- | --- | --- |
| `az bicep build` | Is the template syntactically valid, with real types? | Whether it deploys |
| `az deployment group what-if` | Would ARM accept it here, at these names, in this region? | Whether CI is permitted to do it |
| Gated CI deployment | Does the deployment identity hold the authority? | Whether the objects work |
| The job | Do the datastore and cluster actually work together? | — |

### Sequence

| # | Step | Who | Cost | Gate it clears |
| --- | --- | --- | --- | --- |
| 1 | Write the three resources and the role assignment into `main.bicep`; `az bicep build` | author, local | 0 | Compiles |
| 2 | `az deployment group what-if` against the live resource group | author | 0 | Deployable |
| 3 | Deploy `main.bicep` by hand, as the author | author | 0 | Separates template defects from authorisation defects (R6). **Cluster is created here** |
| 4 | **Observation A**: list the resource group for `*-azurebatch-*` objects; record whether cluster creation was refused | author | 0 | FR-016, resource-group grant (R7) |
| 5 | Read the cluster from the service: node counts all zero | author | 0 | **SC-002** |
| 6 | Push the template change; approve the gate; read the failure | author + CI | 0 | Authority — expect `AuthorizationFailed` |
| 7 | Add **exactly** the named operation to `ci-identity.bicep` with the run id; redeploy the role as the author; re-run the workflow | author | 0 | FR-013, FR-014. **Repeat 6–7 until green** — expect 4–7 cycles |
| 8 | Upload `sample.csv` to the container using the account key | author | ~0 | Setup, not a claim |
| 9 | **Observation B**: attempt to read the blob with `--auth-mode login`; expect refusal; record it verbatim | author | 0 | Establishes the discriminator: the author cannot read the data |
| 10 | Submit the job; watch node allocation | author | **~0.01 €** | **SC-003**, and the cluster can allocate |
| 11 | Read the job output: byte count and sha256 match the known file | author | 0 | **SC-003** — output derived from the bytes |
| 12 | Wait past the idle interval; read the cluster again: back to zero | author | 0 | **SC-004** |
| 13 | **Necessity test**: remove the container grant, re-run the job, record the outcome, restore | author | **~0.01 €** | **D7** — grant load-bearing or inert |
| 14 | Re-check cost across two windows; confirm no node is allocated | author | 0 | **SC-008**, **SC-010**, FR-020, FR-021 |
| 15 | Update `DEPLOY.md` and draft `README.md` text; write both observations down | author | 0 | FR-016, principle IV |
| 16 | **Observation C**, next session: read Cost Management for a full day at rest; is there a load balancer meter? | author | 0 | FR-016, load balancer (R8) |

**Step 3 is the one to justify.** Deploying by hand before letting CI try looks
like it short-circuits the discovery, and it does not. ARM issues the same write
operations on an idempotent redeployment, so CI still fails on exactly the
operations it lacks — nothing is pre-authorised and no operation is skipped.
What it removes is the confounded case: a red run that is a template defect
wearing an authorisation error's clothes. Given each CI cycle costs an approval,
paying once to separate the two classes is worth it.

**Step 16 lands after this session closes.** It is written into the plan rather
than dropped, because an unverified claim that stays unverified is how the cost
model got its § 7 in the first place.

## Cost plan

Per constitution principle I, every step above carries free/billable. Consolidated:

| Item | Amount |
| --- | --- |
| Deployed objects at rest (container, datastore, cluster at 0 nodes) | **0.00 €** |
| Verification job, ~5 min on 1 node | ~0.005 € |
| Necessity test job, ~5 min on 1 node | ~0.005 € |
| Idle tail, 120 s × 2 jobs | ~0.004 € |
| Blob storage for a sample file measured in kilobytes | negligible |
| **Total expected** | **well under 0.10 €**, against the spec's 1 € ceiling |
| **Unknown, being measured** | load balancer at rest, 0 or ~0.30 €/day (R8) |

The worst case is not in this table because it is not a planned cost: a job left
running on 2 nodes for a day is 2.77 €. Step 12 and step 14 both exist to make
sure that does not happen silently.

## Complexity Tracking

No constitution violations. Section intentionally empty.
