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
