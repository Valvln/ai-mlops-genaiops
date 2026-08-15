# Tasks: A place to read data from, and a target to run on

**Feature**: `004-datastore-compute-cluster` · **Date**: 2026-08-15
**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/role-additions.md](./contracts/role-additions.md), [quickstart.md](./quickstart.md)

## How to read this list

Every task carries three labels beyond the standard ones, because in this
repository they decide whether a task may be run at all.

| Label | Meaning |
| --- | --- |
| `[LOCAL]` | Runs on the author's machine or in CI. **Free.** |
| `[AZURE]` | Touches the live subscription. Cost stated where it is not zero. |
| `[AUTHOR]` | Only the author runs it — approvals, commits, portal readings |
| `[CI]` | Runs as the deployment identity, through the approval gate |

**Ordering is evidence, not preference.** Four tasks are only *available* at a
particular moment and produce nothing if moved:

- **T020** (the author cannot read the blob) must precede **T021** (the job).
  Run afterwards, it proves nothing: a job that has already succeeded gives no
  information about who could have read the data.
- **T013** (resource-group grant observation) is available the instant the
  cluster exists and becomes harder to attribute later, once other things have
  touched the resource group.
- **T024** (necessity test) requires a job already known to pass. Run against an
  unproven job, a failure is ambiguous between "the grant mattered" and "the job
  was broken".
- **T027** (load balancer charge) **cannot** be completed in this session at all.
  It needs a full day of the cluster at rest.

**No task commits or pushes.** Commit points are marked as author decisions
between phases; the commands are proposed, the author runs them.

---

## Phase 1: Setup

**Goal**: Everything that can be written and validated without touching Azure.

- [ ] T001 [P] [LOCAL] Create `mlops/datastore-check/sample.csv` — a few rows of trivial CSV, no real data. This is the known file that makes SC-003 checkable.
- [ ] T002 [LOCAL] Record `sample.csv`'s identity in `mlops/datastore-check/README.md`: byte count from `wc -c` and sha256 from `shasum -a 256`, both captured **before** any job exists. Discharges the "known" half of SC-003.
- [ ] T003 [P] [LOCAL] Write `mlops/datastore-check/check_datastore.py` — reads the input path given as an argument, prints byte count, sha256 and row count to stdout. No pandas, no dependencies beyond the standard library: the environment is a curated Azure ML image and the script must not need more than it has.
- [ ] T004 [LOCAL] Write `mlops/datastore-check/job.yml` — command job referencing `check_datastore.py`, a curated environment (no custom image: the workspace has no container registry, deliberately), the cluster as `compute`, and the sample file as an input addressed **through the datastore URI** so a broken datastore breaks the job. Declare the job identity explicitly per [research.md § R4](./research.md).

**Checkpoint**: The job asset exists and is readable. Nothing has been deployed.

---

## Phase 2: Foundational — the template

**Goal**: The three resources and the grant declared and validated. **Blocks
everything after it.**

- [ ] T005 [LOCAL] Add the training data container to `infra/main.bicep` per [data-model.md § 1](./data-model.md): type `Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01`, `publicAccess: 'None'`, parented to the existing account's `default` blob service. Discharges FR-001, FR-004.
- [ ] T006 [LOCAL] Add the datastore to `infra/main.bicep` per [data-model.md § 2](./data-model.md): `@2026-05-01`, `datastoreType: 'AzureBlob'`, `credentials.credentialsType: 'None'`, endpoint from `environment().suffixes.storage`. Comment must say why `None` is a decision and not an omission. Discharges FR-002, FR-003.
- [ ] T007 [LOCAL] Add the compute cluster to `infra/main.bicep` per [data-model.md § 3](./data-model.md): `@2026-05-01`, `identity.type: 'SystemAssigned'`, `Standard_DS1_v2`, `Dedicated`, `minNodeCount: 0`, `maxNodeCount: 2`, `nodeIdleTimeBeforeScaleDown: 'PT120S'`, `remoteLoginPortPublicAccess: 'Disabled'`. Comments must record the quota arithmetic (2 vCPU against a family limit of 6) and that 120 s equals the default and is declared anyway. Discharges FR-005 through FR-011.
- [ ] T008 [LOCAL] Add the container read grant to `infra/main.bicep` per [data-model.md § 4](./data-model.md): `Storage Blob Data Reader` (`2a2b9908-6ea1-4ae2-8e65-a410df84e7d1`, verified against the live tenant 2026-08-15), scoped to the **container**, `principalType: 'ServicePrincipal'`, name from `guid()`. The comment must state that this grant may be inert and that T023 is what decides.
- [ ] T009 [LOCAL] `az bicep build --file infra/main.bicep --stdout > /dev/null` — must exit 0. Report warnings as warnings; the existing `BCP037` suppression on `allowRoleAssignmentOnRG` stays. Constitution principle V gate: **compiles**.
- [ ] T010 [AZURE] [AUTHOR] `az deployment group what-if -g rg-ai300-test01 -f infra/main.bicep`. Free — `what-if` provisions nothing. Expect exactly **four** `Create` entries and no `Modify` on any existing resource. A `Modify` is a defect: this feature adds, it does not alter. Gate: **deployable**.

**Checkpoint**: The template compiles and ARM says it would accept it. Nothing
exists in Azure yet.

> **Author commit point.** One logical change: the template. `infra/main.json`
> is a build output and stays untracked.

---

## Phase 3: User Story 2 — compute exists and costs nothing at rest (P1)

**Goal**: The cluster exists and is observed at zero nodes. Taken before US1
because the cluster is what US1's job runs on.

**Independent test**: Read the deployed cluster's node counts from the service.

- [ ] T011 [AZURE] [AUTHOR] Deploy `infra/main.bicep` by hand: `az deployment group create -g rg-ai300-test01 -f infra/main.bicep`. **Free** — no node is allocated by creating a cluster. Separates template defects from authorisation defects before CI is involved ([research.md § R6](./research.md)); pre-authorises nothing, since ARM reissues the same writes on the CI deployment.
- [ ] T012 [AZURE] [AUTHOR] Confirm the deployment record: `az deployment group list -g rg-ai300-test01 -o table`. A green command is not the record. Discharges the local half of **SC-001**.
- [ ] T013 [AZURE] [AUTHOR] **Observation A — the resource-group grant.** `az resource list -g rg-ai300-test01 --query "[?contains(name,'azurebatch')]" -o table`. Record which of the three `*-azurebatch-*` objects exist (NSG, public IP, load balancer), or, if cluster creation failed, the authorisation error **verbatim**. Both outcomes are findings. Available now and only now. Discharges **FR-016** (first half), **SC-009**.
- [ ] T014 [AZURE] [AUTHOR] **SC-002** — `az ml compute show` and `az ml compute list-nodes` on the cluster. Passes when every node count is 0 and `provisioning_state` is `Succeeded`. **Read the service, not the template**: `min_instances: 0` in the output is the request echoed back and does not satisfy this. Discharges **SC-002**, **FR-017**.
- [ ] T015 [AZURE] [AUTHOR] Confirm the size against live quota: `az ml compute list-usage -g rg-ai300-test01 -w <ws> -o table`. Record the DSv2 family limit and what the cluster now holds. Discharges **SC-005** on the declared side; T019 confirms it on the allocated side.

**Checkpoint**: The cluster exists, rests at zero, and its size is inside quota.

---

## Phase 4: The CI authority loop

**Goal**: The deployment succeeds *as the deployment identity*, with the role
widened by exactly what was refused.

**This is a loop of unknown length.** Between four and seven iterations is the
realistic range ([research.md § R6](./research.md)). It is modelled as a loop and
not as one task per predicted operation, because **the predictions are not
entitlements** — an operation enters the role when a run names it, and a
prediction that never fires never ships.

- [ ] T016 [AZURE] [CI] [AUTHOR] **Repeat until the workflow is green:**
  1. Push the template change to `main`; approve the `azure-deploy` gate. *(The author approves. Never the assistant — FR-012.)*
  2. Read the failure. Confirm it is `AuthorizationFailed` and note the operation it names.
  3. Add **exactly that one operation** to `verifiedActions` in `infra/ci-identity.bicep`, with the run id in the comment.
  4. Record the run id and the quoted error in the confirmed table of [contracts/role-additions.md](./contracts/role-additions.md).
  5. Redeploy the role as the author: `az deployment group create -g rg-ai300-test01 -f infra/ci-identity.bicep --parameters principalId=<sp object id>`.
  6. Re-run the workflow.

  **Free.** Every iteration fails at authorisation, before any resource is touched.

  **Stop conditions that are not "add the operation":**
  - The error is **not** `AuthorizationFailed` → it is a different defect; diagnose it, do not widen the role.
  - The error names an operation **not** on the predicted list → interesting. Record why the prediction missed it before adding it.
  - The `boundary` job goes red → the role is now too **wide**. That is a real defect, unlike a red `deploy` job.
  - Tempted to add a built-in role → forbidden by FR-015. It would end the interruption and end the property the role exists for.

  Discharges **FR-013**, **FR-014**, **FR-015**, **SC-006**.

- [ ] T017 [AZURE] [CI] Confirm the CI deployment reached Azure: a deployment record created **during that run**, state `Succeeded`. A green workflow is not proof that something deployed, and a red one is not proof that nothing did. Discharges **SC-001**.
- [ ] T018 [LOCAL] [AUTHOR] Verify the `boundary` job of `infra-deploy.yml` is still green, and that `ci-identity.bicep` holds no built-in role and no wildcard. This is the check that pushes against the boundary instead of reading it. Discharges **SC-007**.

**Checkpoint**: CI can deploy the template, and its authority grew by exactly
what was refused.

> **Author commit point.** One logical change per operation added is impractical
> across a loop; one commit for the role additions plus its provenance record is
> the honest unit — the provenance file is what preserves the per-operation
> trace.

---

## Phase 5: User Story 1 — the datastore is reachable (P1)

**Goal**: Prove the workspace side can read data through the datastore, as an
identity that is not the author's.

**Independent test**: A job's output checksum equals a checksum recorded before
the job existed.

- [ ] T019 [AZURE] [AUTHOR] Upload the sample file with the **account key**: `az storage blob upload … --auth-mode key`. Negligible cost. This is setup, not a claim — how the file arrives is not what is being tested, and saying so plainly is what keeps the evidence honest.
- [ ] T020 [AZURE] [AUTHOR] **The discriminator. Must run before T021.** Attempt `az storage blob download … --auth-mode login`. **This is expected to FAIL** with `AuthorizationPermissionMismatch`. Capture the error verbatim. It establishes that the author holds `Owner` and no blob data role — so a successful read by the job cannot have used the author's credentials. **If it unexpectedly succeeds, stop**: the discriminator is gone and T021's result would be uninterpretable. Discharges **FR-018**'s precondition, **FR-019**.
- [ ] T021 [AZURE] [AUTHOR] Submit the job: `az ml job create -f mlops/datastore-check/job.yml --stream`. **~0.005 €** (one `DS1_v2` node, a few minutes). While it runs, confirm allocation with `az ml compute list-nodes` — expect ≥ 1 node. Discharges **SC-003**, the allocation half of **SC-004**, and **SC-005** on the allocated side.
- [ ] T022 [AZURE] [AUTHOR] Compare the job's logged sha256, byte count and row count against the values recorded in T002. Passes only on an exact match. **A `Completed` job does not satisfy this** — the spec's edge case is a job that starts, logs and exits zero. Discharges **SC-003**.
- [ ] T023 [AZURE] [AUTHOR] Wait past the 120 s idle interval, then `az ml compute list-nodes` — expect empty, **with no command run to make it so**. A cluster scaled down by hand demonstrates the operator, not the configuration. Discharges **SC-004**.

**Checkpoint**: The datastore and the cluster demonstrably work together.

---

## Phase 6: User Story 4 — the observations (P3)

**Goal**: Answer what was open, by looking. Both outcomes acceptable.

- [ ] T024 [AZURE] [AUTHOR] **The necessity test.** Requires T021–T022 to have passed. Delete the container role assignment, re-run the job, record the outcome, then redeploy `main.bicep` to restore it and confirm the job passes again. **~0.005 €.**
  - **Job fails on authorisation** → the grant is load-bearing; the cluster identity is the reader. Say so in the template comment.
  - **Job succeeds** → the grant is **inert**; the workspace identity's account-scope grant is doing the work. Say so plainly, exactly as `main.bicep` already does for its Key Vault assignment, or remove it.

  This is the check that stops feature 004 shipping a second decorative role assignment. Discharges **D7** ([research.md](./research.md)), and the "no inert authority" property borrowed from feature 003.
- [ ] T025 [AZURE] [AUTHOR] Record Observation A (from T013) in `infra/DEPLOY.md`, with its date and what was actually seen. Update the "Where a failure is expected later" table if the resource-group grant turned out to be needed. Discharges **FR-016**, **SC-009**.
- [ ] T026 [AZURE] [AUTHOR] Note whether a `Microsoft.Network/loadBalancers` resource exists in the resource group while the cluster rests at zero nodes: `az resource list -g rg-ai300-test01 --query "[?type=='Microsoft.Network/loadBalancers']"`. **Existence is not billing** — this is the first of the two steps that settle the question, and it is the half available today.
- [ ] T027 ⏸ **DEFERRED — cannot be completed in this session.** [AZURE] [AUTHOR] Read Cost Management for a full day with the cluster at rest, filtered to `rg-ai300-test01`, looking for a Load Balancer service line on a day when no job ran. Available **24–48 hours** after T011. Then update `docs/exam-notes/compute-cost-model.md` § 7 — the table of unverified claims — with the answer and its date. **If it bills (~0.30 €/day), a cluster is not free at rest and the project's shutdown procedure changes from "leave it" to "delete it at the end of the week".** Carried into the next session's notes rather than dropped. Discharges **FR-016** (second half).

**Checkpoint**: Everything observable today has been observed and written down.

---

## Phase 7: Polish and closing

- [ ] T028 [AZURE] [AUTHOR] **SC-008** — Cost Management → Cost analysis scoped to `rg-ai300-test01`, **comparing two windows**: days before this feature against days spanning it. Passes when the delta is under 1 € and consists only of VM node-hours. A null cost is not a zero, and one window is not a comparison. Discharges **FR-020**.
- [ ] T029 [AZURE] [AUTHOR] **SC-010** — confirm nothing is left running: `az ml compute list-nodes` empty, `az ml online-endpoint list` empty, `az ml batch-endpoint list` empty. **The feature does not close while a node is allocated.** Discharges **FR-021**.
- [ ] T030 [LOCAL] Update `infra/DEPLOY.md`: the new resources and their observed values, the cluster's shutdown procedure, and the CI role additions with their run ids. Its established role is to be revised with what was observed.
- [ ] T031 [LOCAL] Draft candidate `README.md` text in the author's first person, describing what was built and why the size and the identity were chosen as they were. **The author rewrites and commits it** — constitution principle IV.
- [ ] T032 [LOCAL] Close [contracts/role-additions.md](./contracts/role-additions.md): every operation added has a run id, the counts match, the `boundary` job is green.

---

## Dependencies

```text
Phase 1 (T001-T004)  ──┐
                       ├──> Phase 2 (T005-T010) ──> Phase 3 (T011-T015)
                       │                                    │
                       │                                    v
                       │                            Phase 4 (T016-T018)
                       │                                    │
                       └────────────────────────────────────┤
                                                            v
                                                    Phase 5 (T019-T023)
                                                            │
                                                            v
                                                    Phase 6 (T024-T027)
                                                            │
                                                            v
                                                    Phase 7 (T028-T032)
```

**Hard orderings, and what breaks if they are violated:**

| Must precede | Because |
| --- | --- |
| T020 → T021 | The discriminator is worthless once the job has succeeded |
| T013 → anything else touching the resource group | Attribution gets muddier with every later change |
| T022 → T024 | A failure in the necessity test must be unambiguous |
| T011 → T027 (+24 h) | The cost signal needs a full day at rest |

**Parallel opportunities**: T001 ‖ T003 (different files). T005–T008 all touch
`infra/main.bicep` and are therefore **not** parallel. Everything from Phase 3
onwards is inherently serial — it is one subscription and one gate.

---

## Implementation strategy

**MVP** is Phase 2 + Phase 3: a declared cluster resting at zero nodes, verified
from the service. That alone satisfies the harder half of the cost requirement
and answers the resource-group question. It is worth stopping there if the
session runs short — the datastore proof is a clean second sitting.

**The expensive resource here is the author's attention, not money.** Phase 4 is
four to seven approvals and no euros. Phases 5 and 6 are two jobs and about one
euro-cent. Plan the session around the approvals.

**Do not let Phase 7 slip.** T029 is the task that keeps the promise the whole
feature is built on: nothing left running.

---

## Task summary

| Phase | Tasks | Cost | Runs against |
| --- | --- | --- | --- |
| 1 Setup | T001–T004 | 0 | local |
| 2 Template | T005–T010 | 0 | local + `what-if` |
| 3 US2 — cluster at zero | T011–T015 | 0 | Azure |
| 4 CI authority loop | T016–T018 | 0 | Azure, 4–7 gated runs |
| 5 US1 — datastore reachable | T019–T023 | ~0.005 € | Azure |
| 6 US4 — observations | T024–T027 | ~0.005 € | Azure, one deferred |
| 7 Closing | T028–T032 | 0 | Azure + local |
| **Total** | **32** | **~0.01 €** | |

Against the spec's 1 € ceiling, with the load balancer question (0 or
~0.30 €/day) still open until T027.
