# Quickstart: validating feature 005

**Feature**: 005 · **Date**: 2026-08-16

The runnable path from nothing to a verified batch endpoint, in the order the
steps must actually happen. Each step states whether it is **local (free)** or
**Azure (billed)**, per constitution principle I.

Implementation detail belongs in `tasks.md`; this is the validation guide.

---

## Prerequisites

```bash
export PATH="/usr/local/bin:$PATH"      # or az and gh appear uninstalled
cd "/Users/valerioquaranta/Documents/AI-Engineering/Data Science/Development/AI-MLOps-GenAIOps"
```

Environment values, confirmed at rest on 2026-08-16:

| | |
| --- | --- |
| Resource group | `rg-ai300-test01` |
| Workspace | `ai300ml2mgou37pfmjou` |
| Cluster | `ai300-cpu-cluster` — `Steady`, 0/0 nodes |
| Data store | `ai300_training_data` over container `training-data` |
| Storage account | `ai300st2mgou37pfmjou` |

> The workspace name is `ai300ml2mgou37pfmjou`. Guessing a plausible-looking
> name returns `ParentResourceNotFound`, which is a **client-side** error and not
> an authorization refusal — the distinction the runbook warns about.

---

## Phase 1 — 2026-08-16

### 1. Build the pinned local environment · local, free

Python 3.10 with scikit-learn 1.5, matching the curated environment the job runs
in. The author's default interpreter is 3.14, which has no scikit-learn 1.5
wheels.

**Expected**: `uv` reports a resolved environment; the printed scikit-learn
version starts with `1.5`.

### 2. Generate the dataset and record its identity · local, free

**Expected**: a CSV of 2,000 data rows; both classes present in both splits and
neither below 30%; a recorded `sha256` and row count.

> Record the digest **now**. It is what later proves the job read these bytes and
> not something it produced itself.

### 3. Compute the baseline · local, free

**Expected**: a JSON baseline holding parameters, `accuracy`, `f1`, the
prediction vector and its digest, and the installed library versions.

> This must exist **before** the job is submitted. A baseline written afterwards
> proves only that the same code agrees with itself.

### 4. Upload the dataset · Azure, negligible

Uploaded with the **account key**. The author holds no data-plane role on the
storage account, so `--auth-mode login` is refused with
`AuthorizationPermissionMismatch` — established in feature 004 and not a defect.
How the bytes arrive is setup, not a claim under test.

**Expected**: the blob is listed with the byte count recorded in step 2.

### 5. Submit the training job · Azure, billed ≈0.04 €

One submission. The script probes, asserts, trains, tracks and logs the model in
a single activation, because billing runs from node allocation and a separate
probe job would cost roughly what the real job costs.

**Expected, in the log, in order**:

```text
ENV-PROBE-BEGIN … ENV-PROBE-END      ← settles the MLflow question (R1, R2)
DATA-PROBE-BEGIN … DATA-PROBE-END    ← sha256 must equal step 2's digest
METRIC-BEGIN … METRIC-END
```

Job reaches `Completed`, read from the service rather than inferred from the
submitting command's exit code.

**If it exits 3**: the tracking URI was not `azureml`-backed. That is a *result*,
not a defect — it answers FR-009 the other way. The job declares the URI
explicitly and is resubmitted.

> Job logs cannot be downloaded with `az ml job download` on this workspace —
> it fails with `AuthorizationPermissionMismatch` for the same data-plane reason
> as step 4. Read them with the account key from
> `azureml/ExperimentRun/dcid.<job>/user_logs/std_log.txt`.

### 6. Watch the node, once · Azure, free to observe

**Expected**: at least one node allocated during the job; `Steady` at 0/0
afterwards, with no command issued to cause the release.

Read from **ARM**, not from `az ml compute show` — that returns an empty
`node_state_counts`, and an empty field is not a zero (feature 004).

### 7. Compare against the baseline · local, free

**This step is the criterion.** Everything before it produced things; this is
what checks them.

**Expected**: exact agreement on the dataset digest, the parameters and the
prediction-vector digest; metrics within `1e-9`.

**On disagreement**: record it as a finding and investigate. Do **not** widen the
tolerance (FR-016). First suspects, in order — the scikit-learn patch version
printed by the `ENV-PROBE` banner, then whether the `DATA-PROBE` digest matches
step 2.

### 8. Retrieve and verify the model · local, free

Download the artifact **after** the node has been released, load it, and score
the same test inputs.

**Expected**: predictions identical to the baseline's. A listed artifact proves
an upload; only loading it proves a model.

### 9. Derive the phase's billable time · local, free

From the job's own `created` / `start` / `end` timestamps, plus the 120-second
idle tail. Measured on 2026-08-15: billed time ran at 1.98× script time.

**Expected**: a same-day figure at ≈0.082 €/node-hour, plus the warm-window term.
This is SC-006. The **measured** figure is SC-007 and cannot be read today.

### 10. Close Phase 1 · Azure, free to observe

| Check | Required |
| --- | --- |
| Cluster | 0 nodes, `Steady`, from ARM |
| Endpoints | None of any kind |
| Model artifact | **Already downloaded and verified** |

The last row is what lets Phase 2 slip a day without losing anything.

---

## Phase 2 — 2026-08-17

### 11. The deferred readings — first, before anything else · Azure, free

They are the only work in this feature that expires.

- **SC-007** — measured cost for 2026-08-16 against step 9's estimate. Agreement
  within a factor of 2, a threshold fixed before the measurement.
- **SC-013** — the load-balancer duration test, per
  [contracts/batch-scoring.md § 6](./contracts/batch-scoring.md).

> Expect `429` from the Cost Management query API. It is a server response, not a
> client-side failure. The exhausted bucket is the client-type quota with
> `retry-after: 12` — space retries ~20 s apart; sleeping 60 s between attempts
> did not help on 2026-08-16.

### 12. Register the model, twice · local call, free

**Expected**: a first version carrying a name, a version and a run reference;
then a **distinct higher** version, with the first still retrievable.

Registration is metadata over an artifact that already exists, so the second
registration costs nothing — which is why it is demonstrated rather than
asserted.

### 13. Create the endpoint and deployment · Azure, free until scored

The endpoint holds no compute between jobs. The deployment names the registered
version **explicitly**, never `latest`.

**Expected**: endpoint created; deployment provisioned against the existing
cluster; cluster still at 0 nodes, because provisioning a deployment is not
scoring.

### 14. Prepare and upload the scoring input · local + Azure, negligible

**Expected**: rows whose correct predictions **differ**, verified and recorded
before upload (FR-022). A single-class input would be satisfied by a deployment
that returned a constant.

### 15. Score · Azure, billed ≈0.03 €

**Expected**: the scoring job completes and produces one prediction per input
row.

### 16. Compare the predictions · local, free

**This step is the criterion**, and the comparison is against predictions
computed from the **downloaded registered version** — not from the model trained
locally in Phase 1. Comparing against the local model would only re-establish
that scikit-learn is deterministic.

**Expected**: exact match, every row, in input order.

### 17. Close the feature · Azure, free to observe

| Check | Required |
| --- | --- |
| Cluster | 0 nodes, `Steady`, from ARM |
| Batch endpoint | Exists, holds no allocated compute |
| Online endpoints | **None** |
| Compute instances | **None** |

The batch endpoint is kept. It costs nothing idle and it is the deliverable.

**SC-014 remains deferred** to 2026-08-18 — the cost of 2026-08-17 is not
readable on 2026-08-17.

---

## The shape of the whole thing

```text
Phase 1   generate ─► baseline ─► upload ─► JOB ─► compare ─► download ─► verify
  (free)     ▲                      (billed)   ▲                            ▲
             └──────── same bytes ─────────────┘                            │
                                                    exact prediction match ─┘

Phase 2   deferred readings ─► register ×2 ─► deploy ─► SCORE ─► compare
   (free)                        (free)       (free)   (billed)     ▲
                                                                    │
                        against the DOWNLOADED REGISTERED version ──┘
```

Two billed steps in two days. Everything else is free, and every producing step
is matched by a step that checks it against something computed independently.
