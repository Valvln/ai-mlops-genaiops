---

description: "Task list for feature 005 — from a job that runs to a model that answers"
---

# Tasks: From a job that runs to a model that answers

**Input**: Design documents from `/specs/005-training-job-batch-endpoint/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: No unit-test suite. The verification *is* the comparison against a
baseline recorded before the thing under test runs — `compare.py` and the
prediction match are the tests, and they are implementation tasks rather than
test tasks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- **💶**: Task allocates billable compute. Every other task is local and free
- Exact file paths are given in each description

## Organisation: two day-phases, not the template's default

This list is organised by **day**, because the scheduling boundary is the point:
Phase 1 must be able to close on its own if Phase 2 never happens. User-story
grouping is preserved inside each day via the `[USn]` labels.

| Day-phase | Date | Stories | Closes |
| --- | --- | --- | --- |
| **Phase 1** | 2026-08-16 | US1, US2 | SC-001…SC-006, SC-008 |
| **Phase 2** | 2026-08-17 | US5, US3, US4 | SC-007, SC-009…SC-013 |
| *(carried)* | 2026-08-18 | — | SC-014 |

**Cost discipline applies to the order, not only to the count.** The load
balancer bills per hour of cluster warmth ([research.md § R10](./research.md)),
so billed tasks are deliberately adjacent: three jobs inside one warm window cost
barely more than one, three jobs spread across a day cost three times the
warm-window term.

---

# PHASE 1 — 2026-08-16 · training job and its record

**Goal**: a model trained on the cluster from data read through the data store,
with a record proven correct against an independently computed baseline, and the
artifact already on disk.

**Independent test**: submit the job, then run `compare.py`. It exits zero only
if the tracked parameters, metrics and predictions agree with a baseline written
before submission. No registry and no endpoint exist at any point.

**Estimated cost**: ≈0.10 € across 2–3 cluster activations.

## Setup

- [X] T001 Create the feature directory `mlops/training-pipeline/` with a `README.md` placeholder, **and add `mlops/training-pipeline/data/` and `mlops/training-pipeline/downloaded-model/` to `.gitignore`** — the generated dataset and the downloaded artifact are build outputs, and constitution principle II requires derived artifacts to be listed there. Declaring what in the directory is *not* source is part of establishing the directory
- [X] T002 Create `mlops/training-pipeline/pyproject.toml` pinning Python 3.10 and scikit-learn 1.5.x, numpy and pandas, to match curated environment `sklearn-1.5` version 52 (Ubuntu 20.04 / Python 3.10 / scikit-learn 1.5)
- [X] T003 Build the local environment with `uv sync` in `mlops/training-pipeline/`, and record the resolved scikit-learn, numpy and pandas versions into `specs/005-training-job-batch-endpoint/results.md`

> The author's default interpreter is Python 3.14, which has no scikit-learn 1.5
> wheels. `.venv` is already gitignored; the pinned spec is what gets tracked.

## Foundational — the shared ground truth

**⚠️ Blocking**: US1 and US2 both rest on the dataset and the baseline. Nothing
downstream is meaningful until T007 has written the baseline to disk.

- [X] T004 Write `mlops/training-pipeline/generate_data.py` — 2,000 rows × 5 float features + binary label, from `numpy.random.default_rng(42)`, fixed float formatting, per [data-model.md § 1](./data-model.md). Do **not** use `sklearn.datasets.make_classification`
- [X] T005 Run the generator to produce `mlops/training-pipeline/data/training.csv`; assert both classes are present in both the 1500/500 positional splits and neither falls below 30%; record byte count, row count and `sha256` into `results.md`
- [X] T006 Write `mlops/training-pipeline/baseline.py` — loads the CSV, applies the positional split, fits `DecisionTreeClassifier(max_depth=4, random_state=42)`, computes accuracy and F1 on the **test split only**. Take the values from the pinned table in [data-model.md § 2](./data-model.md); `train.py` must read the same ones
- [X] T007 Run the baseline to write `mlops/training-pipeline/baseline.json` holding params, metrics, the prediction vector and its digest, `dataset_sha256`, and installed library versions

> **T007 must complete before T014.** A baseline written after the job has run is
> not a baseline. The file's timestamp is the evidence of ordering.

## User Story 1 — a training run whose record can be trusted (P1)

**Goal**: SC-001, SC-002, SC-003, SC-005.

- [X] T008 [US1] Write the environment probe in `mlops/training-pipeline/train.py` — emit the `ENV-PROBE` block per [contracts/training-run.md § 1](./contracts/training-run.md), reporting `MLFLOW_TRACKING_URI`, the resolved `mlflow.get_tracking_uri()`, and the versions of mlflow, azureml-mlflow, scikit-learn, numpy, pandas
- [X] T009 [US1] Add the tracking assertion to `train.py` — if the resolved URI is not `azureml`-backed, exit **3** without training. This is the load-bearing check: unconfigured MLflow writes to a local `mlruns/` on the node and the job would otherwise exit zero having tracked nothing
- [X] T010 [US1] Add the data probe to `train.py` — emit the `DATA-PROBE` block (mount path, bytes, `sha256`, rows, split sizes), and exit **4** if the digest disagrees with the expected value passed in
- [X] T011 [US1] Add training and tracking to `train.py` — fit the same estimator as `baseline.py`, log params and metrics per [contracts/training-run.md § 3](./contracts/training-run.md), echo the `METRIC` block at full precision, and log the model in **MLflow format** (required for Phase 2's no-code deployment)
- [X] T012 [US1] Write `mlops/training-pipeline/train-job.yml` — curated environment pinned to `azureml://registries/azureml/environments/sklearn-1.5/versions/52`, input as `uri_file` addressed through `azureml://datastores/ai300_training_data/paths/...` with `ro_mount`, `compute: azureml:ai300-cpu-cluster`, and `identity: type: managed`
- [X] T013 [US1] Upload `training.csv` to the `training-data` container with `--auth-mode key`, and confirm the listed byte count equals T005's. The account key is required because the author holds no data-plane role — established in feature 004, and setup rather than a claim under test
- [X] T014 [US1] 💶 Submit the training job with `--stream`. **One submission**: the script probes, asserts, trains, tracks and logs in a single cluster activation, because billing runs from allocation
- [X] T015 [US1] While the job runs, read the cluster from **ARM** and record at least one allocated node — `az ml compute show` returns an empty `node_state_counts`, and an empty field is not a zero (SC-002, first half)
- [X] T016 [US1] Read the job's terminal status **from the service**, not from the submitting command's exit code (SC-001)
- [X] T017 [US1] Read `user_logs/std_log.txt` from `azureml/ExperimentRun/dcid.<job>/` using the **account key** — `az ml job download` fails with `AuthorizationPermissionMismatch` on this workspace for the same data-plane reason as T013
- [X] T018 [US1] Record the `ENV-PROBE` answer into `results.md`: whether the workspace configured the tracking URI or the job had to declare it, **with the observed value and what would have been seen had the answer been the other one** (SC-005, settles FR-009 and [research.md § R1](./research.md))
- [X] T019 [US1] Verify the `DATA-PROBE` `sha256` equals T005's recorded digest — this is what stops the whole verification passing on data the job supplied to itself
- [X] T020 [US1] Write `mlops/training-pipeline/compare.py` — exact match on `dataset_sha256`, params and the prediction-vector digest; `1e-9` absolute on accuracy and F1; non-zero exit on any disagreement, per [contracts/training-run.md § 5](./contracts/training-run.md)
- [X] T021 [US1] Run `compare.py` against `baseline.json` and the tracked run. **This is the criterion** (SC-003). On disagreement: record it as a finding and investigate — first the scikit-learn patch version from the `ENV-PROBE` banner, then T019's digest. **Do not widen the tolerance** (FR-016)

## User Story 2 — the trained model can be got back out (P1)

**Goal**: SC-004. Also what makes Phase 2 startable from a verified input.

- [X] T022 [US2] Download the model artifact from the completed run **after** the node has been released, into `mlops/training-pipeline/downloaded-model/` (gitignored — a build output, not source)
- [X] T023 [US2] Load the downloaded model in the pinned local environment and score the same test inputs; require the prediction vector to match `baseline.json` **exactly** (SC-004). A listed artifact proves an upload happened; only this proves a model

## Contingency — only if a refusal arrives

Skip entirely unless T014 or T022 is refused. [research.md § R3](./research.md)
predicts this will **not** fire, at deliberately low confidence.

> **DID NOT FIRE — 2026-08-16.** Left unticked deliberately: these tasks were not
> performed, and ticking them would claim work that did not happen. Job
> `placid_fish_sdyy5dh0yl` did fail, but on a `404` from an unimplemented MLflow 3
> endpoint, not on a refusal — and the same run had already written params,
> metrics and tags to the workspace, so the write path was demonstrably
> authorised. R3's low-confidence prediction was right: feature 005 needed no role
> assignment, no `main.bicep` change and no gated deployment. Establishing *that*
> was T024's actual job, and it is the one step of this block that was carried
> out. See [results.md](./results.md).

- [ ] T024 [US1] Establish the failure is a **server-side refusal** — not a client-side failure, a wrong path, or an empty result (FR-025). Feature 004 recorded that not every refusal says `AuthorizationFailed`: the same run returned an ARM `AuthorizationFailed` and an Azure ML `UserError` with `ForbiddenError` only in an inner error
- [ ] T025 [US1] Add **exactly** the operation and scope the refusal names, to the principal it names, as a role assignment in `infra/main.bicep`, with the failing job name as its provenance comment. Never a built-in role, never a wildcard
- [ ] T026 [US1] Validate with `az bicep build infra/main.bicep`, and report the change as **compiled, not deployed**, until the gated run succeeds
- [ ] T027 [US1] Propose the commit and the push that triggers the gated deployment. **The author approves the gate** — never approve it on their behalf

## Phase 1 closure

**⚠️ Phase 1 closes here whether or not Phase 2 happens.** If the day has run
out, everything below still gets done; Phase 2 slips.

- [X] T028 Verify the cluster returned to zero nodes unprompted, read from ARM, and record the transition (SC-002, second half). **Then re-read the run's parameters and metrics from the workspace, with the node gone** — this settles FR-012, and it is only meaningful in this order: a record that survives the compute that produced it is exactly what distinguishes real tracking from a local `mlruns/` directory that died at scale-down
- [X] T029 Confirm no endpoint of any kind exists — online, batch, or compute instance (SC-008)
- [X] T030 Derive billable node time from the job's own `created`/`start`/`end` timestamps plus the 120-second idle tail, and convert at ≈0.082 €/node-hour plus the warm-window term (SC-006). Record the **job-active window**, which Phase 2's SC-013 needs as an input
- [X] T031 [P] Write `mlops/training-pipeline/README.md` — what was built, the observed values, and the answer to the MLflow tracking question
- [X] T032 [P] Write the Phase 1 section of `specs/005-training-job-batch-endpoint/results.md`, including any prediction from `research.md` that was contradicted, recorded as the entry rather than as a quiet correction
- [ ] T033 Propose commits for the author: one for the pipeline scripts, one for the workload definition, one for the results. One logical change each

---

# PHASE 2 — 2026-08-17 · registry and batch endpoint

**Goal**: the verified model registered with a version and served by a batch
endpoint whose predictions are checked against the registered model itself.

**Independent test**: score a prepared input through the endpoint and match it
row for row against predictions computed from the **downloaded registered
version**.

**Estimated cost**: ≈0.07 € across 1–2 cluster activations.

## User Story 5 — the deferred readings (P3, but first in the day)

**⚠️ These run before anything else.** They are the only work in this feature
that expires: the cost window for 2026-08-16 becomes readable today, and its
interpretation needs T030's job-active window.

- [ ] T034 [US5] Read Cost Management for the 2026-08-16 window, grouped by meter. **Space retries ~20 s apart** — the API returns `429` from the client-type quota with `retry-after: 12`, and sleeping 60 s between attempts did not help on 2026-08-16. A `429` is a server response, not a client-side failure
- [ ] T035 [US5] Compare the measured 2026-08-16 cost against T030's estimate; agreement within a **factor of 2**, the threshold fixed in [research.md § R10](./research.md) before the measurement was taken (SC-007)
- [ ] T036 [US5] Divide the Load Balancer meter by its assumed rate and compare the implied duration against T030's job-active window plus a ~2 h tail (2–5 h) versus a full day (~24 h), per [contracts/batch-scoring.md § 6](./contracts/batch-scoring.md) (SC-013)
- [ ] T037 [US5] Record the conclusion **with its caveat**: the rate in the denominator is an Azure list price recalled from memory, not a measured rate. State the arithmetic. If the answer is "billed at rest", update the shutdown procedure in `docs/exam-notes/compute-cost-model.md` § 6 for the rest of the project
- [ ] T038 [US5] Update `docs/exam-notes/compute-cost-model.md` § 7 and § 7.2 with the dated outcome of both readings

## User Story 3 — the model is registered, and the registry versions (P2)

**Goal**: SC-009, SC-010. Free — registration is metadata over an existing artifact.

- [ ] T039 [US3] Register the model **from the completed run**, not from the local download, so the entry carries the run reference as a property of the record rather than as a note (FR-017)
- [ ] T040 [US3] Read the entry back and confirm it carries a name, a version and a reference identifying the Phase 1 run (SC-009)
- [ ] T041 [US3] Register the same model a second time under the same name; confirm a **distinct higher version** and that version 1 is still retrievable afterwards (SC-010). Reading a version field proves a field exists, not that the registry versions

## User Story 4 — the model answers in bulk, and the answers are right (P2)

**Goal**: SC-011, SC-012.

- [ ] T042 [US4] [P] Write `mlops/training-pipeline/batch-endpoint.yml` — batch kind. A real-time endpoint must not be created at any point (FR-019)
- [ ] T043 [US4] [P] Write `mlops/training-pipeline/batch-deployment.yml` — names the registered version **explicitly, never `latest`**; `compute: azureml:ai300-cpu-cluster`; `instance_count: 1`; **no scoring script** (no-code, derived from the MLflow model); output action append-row
- [ ] T044 [US4] Create the endpoint with `az ml batch-endpoint create`
- [ ] T045 [US4] Create the deployment with `az ml batch-deployment create`
- [ ] T046 [US4] Confirm the cluster is **still at zero nodes** after the deployment is provisioned — provisioning a deployment is not scoring, and a node here would mean the batch endpoint is billing when it should not
- [ ] T047 [US4] [P] Build the scoring input at `mlops/training-pipeline/scoring-input/` from test-split rows, and **verify both predicted classes are present** before upload (FR-022). A single-class input would be satisfied by a deployment returning a constant
- [ ] T048 [US4] Download the **registered version** from the registry and compute its predictions on the scoring input locally — this is the right-hand side of the comparison, and it must be the registered model, not the Phase 1 local model. **Depends on T047**: there is no input to predict on until the scoring set exists
- [ ] T049 [US4] Upload the scoring input to the `training-data` container with `--auth-mode key`
- [ ] T050 [US4] 💶 Invoke the batch endpoint on the prepared input and wait for the scoring job to complete
- [ ] T051 [US4] Retrieve the scoring output file
- [ ] T052 [US4] Compare the endpoint's predictions against T048's, **row for row, exact match, in input order** (SC-011). A completed scoring job is not evidence — it proves compute ran

## Phase 2 closure

- [ ] T053 Verify closure from the service: cluster 0 nodes `Steady` from ARM; batch endpoint exists and holds **no allocated compute**; **no** online endpoint; **no** compute instance (SC-012). The batch endpoint is **kept** — it costs nothing idle and it is the deliverable
- [ ] T054 [P] Update `mlops/training-pipeline/README.md` with the registration and serving outcomes
- [ ] T055 [P] Write the Phase 2 section of `results.md`, including the [research.md](./research.md) prediction scorecard — predictions that did not fire stay in the table marked as such rather than being deleted
- [ ] T056 [P] Draft candidate `README.md` text in the author's **first person** for review (constitution principle IV — the author rewrites and commits it)
- [ ] T057 Check `git log --oneline origin/main..005-training-job-batch-endpoint` before the branch is closed, and confirm `main` will not be left declaring something Azure does not have — the disalignment that cost 15/08 several hours
- [ ] T058 Propose commits for the author, one logical change each
- [ ] T059 Carry **SC-014** forward to 2026-08-18: the cost of 2026-08-17 is not readable on 2026-08-17. Record it in the handover, not as done

---

## Dependencies

```text
Setup (T001-T003)
    │
    ▼
Foundational (T004-T007)  ── baseline.json written BEFORE any submission
    │
    ├──────────────► US1 (T008-T021) ──► US2 (T022-T023)
    │                    │
    │                    └── contingency T024-T027, only on refusal
    │
    ▼
Phase 1 closure (T028-T033)   ◄── CLOSES ALONE. Phase 2 may slip past here.
    │
    ▼
US5 (T034-T038)   ── needs T030's job-active window; expires if not read today
    │
    ▼
US3 (T039-T041)   ── needs US2's verified artifact
    │
    ▼
US4 (T042-T052)   ── needs US3's registered version
    │
    ▼
Phase 2 closure (T053-T059)
```

**Story independence**: US1 and US2 together form a complete, deliverable
increment — the Domain 2 tracking objective — with no registry and no endpoint in
existence. US5 is independent of everything except T030 and could run on any
later day. US3 depends on US2's artifact; US4 depends on US3's version.

## Parallel opportunities

Genuinely few, because the feature is a chain of verifications and each link
checks the previous one.

- **T031, T032** — README and results, different files, after T030
- **T042, T043** — endpoint and deployment definitions, different files, both before either is applied
- **T054, T055, T056** — three documents, different files

**T014 and T050 must not be parallelised with anything**, and not because of file
conflicts: they allocate billable compute, and an unattended job is the one
outcome the cost principle forbids.

## Implementation strategy

**MVP = Phase 1 = US1 + US2.** A trained model, a record proven correct against
an independent baseline, and the artifact on disk. That is the Domain 2 tracking
objective delivered whole, and it is deliberately closable on 2026-08-16 with
nothing left running.

**If the day runs short**, the cut line is after T033. What must never be left
behind: an allocated node, a half-defined job, or an unretrieved artifact — the
last because T022 is what lets Phase 2 start from a verified input instead of
re-running a billed job.

**Order within Phase 2 is chosen by expiry, not by priority.** US5 is P3 and goes
first, because a cost window that is not read on the day it becomes readable
becomes a window that has to be reconstructed later.
