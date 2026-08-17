# Results: From a job that runs to a model that answers

**Feature**: 005 · Observed values, recorded as they were measured.

Predictions from [research.md](./research.md) are settled here — including the
ones that were wrong, which are kept as entries rather than quietly corrected.

---

## Phase 1 — 2026-08-16

### Local environment (T003)

Built with `uv sync` in `mlops/training-pipeline/`, pinned to match curated
environment `sklearn-1.5` version 52.

| Component | Resolved locally | Curated environment claims |
| --- | --- | --- |
| Python | 3.10.20 | 3.10 |
| scikit-learn | 1.5.2 | 1.5 (no patch published) |
| numpy | 1.26.4 | — |
| pandas | 2.3.3 | — |
| mlflow | 2.22.5 | — |
| Platform | macOS 15.3.2, x86_64 | Ubuntu 20.04 |

The platform row is the one that matters. Local metrics are computed on macOS
against a job running in an Ubuntu container, which is why the estimator was
chosen to avoid BLAS entirely ([research.md § R4](./research.md)). The remote
versions in the right-hand column are what the curated environment *claims*; the
`ENV-PROBE` banner reports what it actually installed, and the two are compared
at T018.

### The dataset (T005)

| Property | Value |
| --- | --- |
| Path | `mlops/training-pipeline/data/training.csv` |
| Bytes | 99,076 |
| Rows | 2,000 plus header |
| `sha256` | `9130b02593b6ce3fe84bbef7543b9397b96e05e36d131afa4b8daaf84bb60384` |

Class balance, against the 30% floor FR-003 sets:

| Split | Class 0 | Class 1 |
| --- | --- | --- |
| Train (rows 1–1500) | 49.5% (743) | 50.5% (757) |
| Test (rows 1501–2000) | 51.4% (257) | 48.6% (243) |

**Reproducibility checked, not assumed.** The generator was run a second time and
the output compared byte for byte against the first: identical, same digest. That
settles FR-001 locally — the recorded procedure reproduces the exact bytes, so
the seed and the fixed float formatting are doing what [research.md § R5](./research.md)
claimed for them.

### The local baseline (T007)

Written **2026-08-16 17:51:23 UTC**, before any job submission. The timestamp is
the evidence of ordering, and it is recorded here for that reason rather than for
completeness.

| Quantity | Value |
| --- | --- |
| `accuracy` | `0.854` |
| `f1` | `0.8488612836438924` |
| `predictions_sha256` | `495d5e534a0df9dcdcf499d09206b14e0398748b92068f32d542bfb0178f0163` |
| `dataset_sha256` | `9130b0…60384` — matches T005 |

Accuracy at 0.854 is what `max_depth: 4` was pinned to produce: clear of 1.0,
which would make the comparison undiscriminating, and clear of the ~0.5 a coin
would score. A criterion that cannot distinguish a working model from a broken
one has the same defect as one that cannot fail.

### The two jobs

Two cluster activations, within the 2–3 that [research.md § R10](./research.md)
budgeted. The first failed, and it failed usefully.

| | `placid_fish_sdyy5dh0yl` | `placid_knot_z03v76ysql` |
| --- | --- | --- |
| Created | 16:17:14 UTC | 16:29:09 UTC |
| Script window | 16:19:20 → 16:23:38 (4m18s) | 16:31:47 → 16:36:17 (4m30s) |
| Status | **Failed** | **Completed** |
| Reached | params, metrics, tags tracked | everything |

### Why the first job failed — and what it was not (T024–T027 not fired)

```
mlflow.exceptions.MlflowException: API request to endpoint
/api/2.0/mlflow/logged-models failed with error code 404 != 200
```

`mlflow.sklearn.log_model` on MLflow **3.13.0** — the version the curated
environment actually ships — routes model logging through the LoggedModel API
introduced in MLflow 3. The Azure ML tracking server does not implement that
endpoint.

**This is not an authorization refusal, and establishing that mattered before
touching anything.** The contingency path T024–T027 exists for a server-side
refusal, and reaching for it here would have added a role assignment that fixed
nothing. Three things separate this failure from that one:

- the status code is `404`, not `403`, and no principal is named;
- the *same run* had already written params, metrics and tags to the workspace's
  default store — under `identity: managed`, on a container the cluster identity
  holds no grant for. So the write path was demonstrably working;
- `mlflow.log_artifacts` — the classic artifact API — succeeded on the second
  job against the same store.

**R3's prediction is therefore confirmed**: run history and artifact upload are
performed with the run's own token, not the compute identity's grant. Feature 005
needed **no new role assignment**, no `main.bicep` change and no gated
deployment.

### Two defects of mine that the failure exposed

Recorded as findings rather than quietly fixed, because both are the kind that
would have survived into Phase 2.

1. **The `METRIC` block was emitted after the model was written.** The contract
   duplicates metrics into the log specifically to have a path that survives when
   the tracking or artifact path does not — and putting the block last threw that
   away. Job one computed correct metrics, tracked them, and left a log with no
   `METRIC` lines in it. Now emitted before the model is written.
2. **One artifact mechanism with no fallback and no reported outcome.** The
   rewrite writes the model to `./outputs/`, which Azure ML uploads on its own
   with no MLflow API involved, *and* attempts `mlflow.log_artifacts`, printing
   `artifact_api=OK` or `=FAILED` rather than assuming. That turned the second
   submission into a question with an answer instead of a retry.

**Both mechanisms worked**, which is itself the finding — the run carries the
model twice, at `model/` and at `outputs/model/`:

```
ExperimentRun/dcid.placid_knot_z03v76ysql/model/MLmodel
ExperimentRun/dcid.placid_knot_z03v76ysql/outputs/model/MLmodel
```

### The environment, as observed rather than as claimed (T018 — settles FR-009)

| | Curated environment (observed) | Local baseline |
| --- | --- | --- |
| `MLFLOW_TRACKING_URI` | **present**, `azureml://northeurope.api.azureml.ms/...` | absent |
| mlflow | **3.13.0** | 2.22.5 |
| azureml-mlflow | present | present |
| scikit-learn | 1.5.2 | 1.5.2 |
| numpy | 1.22.4 | 1.26.4 |
| pandas | 1.5.3 | 2.3.3 |
| Python | 3.10.20 | 3.10.20 |
| Platform | Linux 6.8.0-azure, glibc 2.39 | macOS 15.3.2 |

**R1 is settled: the workspace configures the tracking URI itself.** The job did
not have to declare it. `MLFLOW_TRACKING_URI` was injected into the container and
`mlflow.get_tracking_uri()` resolved to the same `azureml://` value.

**What would have been seen had the answer been the other one**, since the
requirement is to know rather than to be reassured: `mlflow_tracking_uri_env=ABSENT`
and a resolved URI of `file:///…/mlruns`. That is not hypothetical — it is
exactly what the same script printed when run locally, where it exited **3**
without training. The check was watched failing before it was trusted passing.

**R2 is settled with a correction**: mlflow and azureml-mlflow are both present,
as predicted — but at MLflow **3.x**, which the research did not anticipate and
which is the direct cause of job one's failure. The prediction "the environment
contains MLflow" was right and insufficient; the version was the load-bearing
detail.

### The comparison — SC-003, the criterion itself

`compare.py` was exercised in **four** directions before any job ran: agreement
on a correct log, and disagreement on a metric drifted by 1e-8, on a wrong
dataset digest, and on a wrong prediction digest. A first attempt to test the
failure direction used a drift of 3.6e-10 and passed — correctly, being inside
the 1e-9 tolerance — and was thrown out as a badly built test rather than
recorded as a result.

Against `placid_knot_z03v76ysql`, from both sources and cross-checked between
them:

```
AGREEMENT — params, metrics and the prediction vector all match the baseline.
```

| Compared | Result |
| --- | --- |
| `dataset_sha256`, job log vs baseline | exact |
| Parameters, tracked run vs baseline | exact, key by key |
| `accuracy`, `f1` | equal, well inside 1e-9 |
| Prediction vector digest | **exact** |
| Job log `METRIC` block vs tracked run | agree |

**R4 is confirmed, and this is the result the estimator choice was made to buy.**
The prediction vector computed on macOS with numpy 1.26.4 and the one computed on
Ubuntu with numpy 1.22.4 are **identical, all 500 of them** — not close. A
`LogisticRegression` would have put an iterative BLAS optimiser between those two
platforms.

### The model comes back out — SC-004

Downloaded with the account key **after** the cluster reached zero nodes, loaded
in the pinned local environment, and scored on the same test rows:

```
EXACT MATCH        True
vector equal       True
accuracy re-scored 0.854 == baseline 0.854
```

MLflow warned about seven dependency mismatches while loading, including the
mlflow major version itself (`current: 2.22.5, required: 3.13.0`). It loaded and
predicted identically anyway. Worth recording because it is a warning that looks
like a problem and is not — and because a decision tree is why: there is no
numerical library in the prediction path to disagree.

### Closure (T028, T029)

| Check | Reading |
| --- | --- |
| Cluster nodes | `currentNodeCount 0`, `allocationState Steady`, all state counts zero |
| Scale-down | unprompted, completed 16:41:47 UTC |
| Run readable with the node gone | **yes** — params and metrics re-read after release |
| Online endpoints | none |
| Batch endpoints | none |
| Compute instances | none — `ai300-cpu-cluster` is the only compute |

The middle row is FR-012, and the order is the whole point: a record read while
the node still exists proves nothing about surviving it.

**A note on reading node counts.** `az ml compute show` returns
`node_state_counts: None` on this workspace, and an empty field is not a zero.
Every node reading here comes from ARM directly. During job two that read showed
`preparingNodeCount: 1` a full minute before the script started running — which
is the billing rule made visible rather than argued.

### Cost (T030 — SC-006)

Node windows, from the ARM polling captured during the run:

| | Node window | Script time | Billed / script |
| --- | --- | --- | --- |
| `placid_knot_z03v76ysql` | 9.2–11.7 min, midpoint **10.5** — *directly observed* | 4.5 min | **2.32×** |
| `placid_fish_sdyy5dh0yl` | ~9.5 min — *inferred, not observed* | 4.3 min | ~2.21× |

Job one's window is an inference, not a measurement: ARM was not polled during
it. It is stated as such rather than presented alongside the observed figure as
though the two were the same kind of number.

| Term | Quantity | Rate | Cost |
| --- | --- | --- | --- |
| Node time | 20.0 min = 0.333 node-hours | 0.082 €/node-hour | **0.027 €** |
| Warm window, observed | 0.38 h (16:18:45 → 16:41:47) | 0.025 €/h | 0.010 € |
| Warm window, with a ~2 h tail | 2.38 h | 0.025 €/h | 0.060 € |

**Phase 1 estimate: 0.037 € if the balancer is torn down promptly, 0.087 € if it
carries the ~2 h tail.** Against R10's ≈0.10 € for the phase, both ends are
inside the factor-of-2 agreement threshold fixed before the measurement.

**The 2.2–2.3× ratio independently reproduces this morning's 1.98×**, measured on
feature 004's job in a separate session. Two jobs, a different script, the same
rule: billing runs from allocation, so a job's floor is roughly twice its script
time, and the fix is fewer longer jobs rather than shorter ones.

**Job-active window for 2026-08-16, which Phase 2's SC-013 consumes**:
**16:18:45 → 16:41:47 UTC, ≈23 minutes (0.38 h).** No other compute ran on this
subscription today — the morning session was a cost read with no job. So the
load-balancer arithmetic tomorrow divides the measured LB meter by its rate and
compares the implied duration against ≈2.4 h (0.38 h warm + ~2 h tail) versus
~24 h.

### Prediction scorecard — Phase 1

| Prediction | Outcome |
| --- | --- |
| R1 — the workspace injects the tracking URI | ✅ confirmed |
| R2 — the curated environment contains mlflow and azureml-mlflow | ⚠️ **confirmed but incomplete** — it ships MLflow 3.x, and the version was the detail that mattered |
| R3 — no authorization refusal; the run's own token writes | ✅ confirmed, held at low confidence and right |
| R4 — identical predictions across platforms, not merely close | ✅ confirmed, exactly |
| R5 — the dataset regenerates byte for byte | ✅ confirmed |
| R6 — local pin matches the image's scikit-learn | ✅ 1.5.2 on both; numpy and pandas differ and did not matter |
| R10 — cost within a factor of 2 of ≈0.10 € | ✅ on the estimate; the **measured** figure is SC-007, deferred to 2026-08-17 |

R7, R8, R9 and R11 belong to Phase 2 and stay in the table unsettled rather than
being removed.

---

## Phase 2 — 2026-08-17

### The deferred cost readings (T034–T038)

Read **2026-08-17 05:53 UTC**, covering the 2026-08-16 window. Grouped by meter,
not by service total — the whole test depends on separating the balancer from the
virtual machine on a day when both were active. The query returned on the first
attempt; no `429` this time.

| Meter | 15/08 € | 16/08 € |
| --- | --- | --- |
| Load Balancer · Standard Included LB Rules and Outbound Rules | 0.043925 | 0.026291 |
| Storage · P10 LRS Disk | 0.011014 | **0.025422** |
| Load Balancer · Standard Data Processed | 0.001620 | **0.021668** |
| Virtual Machines · D1 v2/DS1 v2 | 0.024089 | 0.016381 |
| Virtual Network · Standard IPv4 Static Public IP | 0.008785 | 0.005258 |
| Storage · write / read / list operations | 0.002085 | 0.001297 |
| **Total** | **0.091197** | **0.096347** |

### SC-013 — the load balancer is NOT billed at rest

Two arguments, and the first needs no rate at all.

**A. The calendar argument.** A charge incurred at rest is a function of elapsed
time, and 15/08 and 16/08 are both 24-hour days. The balancer billed **0.043925 €**
on one and **0.026291 €** on the other — a 1.67× difference. A resting charge
cannot vary with what was done during the day, because nothing was being done.
So the meter tracks activity.

**B. The arithmetic, at the rates § 7.2 of the cost model already records**
(≈0.021 €/h for LB rules, ≈0.0042 €/h for the static IP):

| Day | LB implied | IP implied | Agree? |
| --- | --- | --- | --- |
| 15/08 | 2.09 h | 2.09 h | ✅ |
| 16/08 | **1.25 h** | **1.25 h** | ✅ |

| 16/08 hypothesis, fixed in [research.md § R11](./research.md) before the reading | Implied duration |
| --- | --- |
| Billed only while warm | ≈2.4 h (0.38 h warm + ~2 h tail) |
| Billed at rest as well | ≈24 h |
| **Observed** | **1.25 h** |

**The answer is "only while warm", by a factor of 19 against the alternative.**
The observed figure is even *below* the warm-only hypothesis, because the tail
was shorter than assumed: 1.25 h − 0.38 h of job window leaves a tail of ≈52
minutes, against the ~2 h carried over from the 15/08 reading.

**The inherited weakness, and why it does not sink the conclusion.** R11 recorded
that the rate in the denominator is an Azure list price recalled from memory, not
a measured rate, and that a wrong rate scales the implied duration
proportionally. It survives for two reasons:

- For "billed at rest" to be true, the LB rate would have to be **0.0011 €/h**,
  19× below the recalled value.
- **And the public IP rate would have to be wrong by the same factor**, because
  the two meters — with independently recalled rates — agree on the implied
  duration to two decimal places, on both days. A systematic error that lands two
  separate rates on the same wrong answer twice is not a plausible failure.

That agreement is the part that makes the test usable, and it was not designed
in: it fell out of the data.

**Consequence for the project**: the shutdown procedure in
`docs/exam-notes/compute-cost-model.md` § 6 **does not change**. A cluster at
`min_nodes: 0` may be left in place between sessions; it is genuinely free at
rest. Deleting it at the end of a week would buy nothing and would cost the
90-day Key Vault name lock on any teardown that took the resource group with it.

### SC-007 — the estimate agreed, and three of its parts were wrong

| | Estimated 16/08 | Measured | |
| --- | --- | --- | --- |
| Total | 0.037 – **0.087 €** | **0.096347 €** | **1.11×** — inside the factor-of-2 threshold ✅ |

The threshold was fixed in R10 before the measurement, and the upper end of the
estimate passes it comfortably. The lower end — the "no LB tail" case — is 2.60×
off and is refuted.

**But the total is right partly by cancellation, and that is worth more than the
pass.** Component by component:

| Term | Estimated | Measured | |
| --- | --- | --- | --- |
| VM + P10 OS disk | 0.0273 | 0.0418 | **1.53× under**-estimated |
| LB rules + public IP | 0.0596 | 0.0315 | **1.9× over**-estimated |
| LB · Standard Data Processed | **0.0000** | 0.0217 | **term absent from the model** |

A total that lands within 11% while its three components are wrong by 1.5×, 1.9×
and infinitely is exactly the shape of check this repository has learned to
distrust: it passes, and it would have passed just as well if the model were
nonsense. The pass is recorded; so is the fact that it proves less than it looks.

### Two corrections the reading forces on the cost model

**1. The OS disk outlives the node, and it is now the largest single node-side
term.** On 16/08 the P10 disk billed **more than the virtual machine** — 0.025422
against 0.016381:

| | disk / VM | Implied disk lifetime | Node time |
| --- | --- | --- | --- |
| 15/08 (3 jobs) | 0.46 | ≈0.41 h | ≈0.42 h |
| 16/08 (2 jobs) | **1.55** | ≈0.94 h | ≈0.33 h |

The blended "≈0.082 €/node-hour for VM + P10 disk" rate assumed the two bill for
the same duration. They do not: on 16/08 the disk was charged for roughly **three
times** the node's lifetime. That is per-activation overhead — the disk is
created before the node is usable and released after it is gone — so two short
activations pay it twice.

**This strengthens "fewer, longer jobs" with a second, independent mechanism.**
The first was that provisioning is billed; the second is that the disk overhead
is per activation and does not shrink with a shorter script.

**2. `Load Balancer · Standard Data Processed` scales with what the job pulls,
not with time.** It went from 0.001620 € to 0.021668 € — **13×** — while the
balancer's own hours went *down*. The difference is what crossed the wire:
2026-08-16's jobs pulled the `sklearn-1.5` curated image and pushed model
artifacts back, twice. At 22.5% of the day's bill it is not a rounding term, and
the planning model had no place for it at all.

### Prediction scorecard — Phase 2, part one

| Prediction | Outcome |
| --- | --- |
| R11 — the warm-only hypothesis, at 2–5 h | ⚠️ **direction right, magnitude wrong.** Warm-only is confirmed decisively, but the observed 1.25 h falls *below* the predicted 2–5 h band |
| R10 — measured within a factor of 2 of the estimate | ✅ 1.11× on the total, with the component caveat above |

R7, R8 and R9 remain open until the endpoint is built.
