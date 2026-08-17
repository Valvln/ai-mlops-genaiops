# Data Model: From a job that runs to a model that answers

**Feature**: 005 · **Date**: 2026-08-16

The entities this feature creates, what each is made of, and — for every one of
them — **what would make it look correct while being wrong**. That last column is
the reason this document exists; each entity in this feature has a cheap
appearance that a careless check would accept.

---

## 1. Training dataset

Synthetic tabular data, generated locally once and uploaded. The bytes are the
shared ground truth between the local baseline and the remote job.

| Field | Type | Notes |
| --- | --- | --- |
| `f0` … `f4` | float | Five numeric features |
| `label` | int, 0 or 1 | Binary target |

**Shape**: 2,000 rows plus a header. First 1,500 rows are the training split,
last 500 the test split — **positional, with no RNG involved** ([research.md § R5](./research.md)).

**Generation rules**:

- `numpy.random.default_rng(42)`, whose stream is guaranteed reproducible across
  NumPy versions. Not `sklearn.datasets.make_classification`, whose internals are
  free to change between releases.
- Floats written with fixed formatting, so the CSV bytes are a function of the
  seed and nothing else.
- Rows are already in random order by construction, which is what makes the
  positional split unbiased.

**Validation**:

- Both classes present in both splits, neither below 30% — otherwise accuracy is
  degenerate and the comparison loses discriminating power (FR-003).
- Content digest and row count recorded **before** anything is uploaded.

**How it could look right and be wrong**: the job could train on data it
generated itself and produce metrics matching the baseline exactly. Guarded by
FR-004 — the job records the mount path and a digest of the bytes it read, and
that digest must equal the one recorded before the upload.

---

## 2. Local baseline

Computed on the author's machine, from the same file, in the pinned environment,
**before the job is submitted**. It is the only artifact in this feature capable
of contradicting a tracked result.

| Field | Type | Notes |
| --- | --- | --- |
| `dataset_sha256` | string | Digest of the exact bytes trained on |
| `dataset_rows` | int | Row count excluding the header |
| `params` | mapping | Seed, `max_depth`, split sizes, estimator name |
| `metrics` | mapping | At least accuracy and F1 on the test split |
| `predictions` | int array | Predicted class per test row, in row order |
| `library_versions` | mapping | scikit-learn, NumPy, pandas as actually installed |

**Persisted to disk as JSON**, so the comparison later reads a recorded file
rather than re-deriving values in the same process that checks them.

### Pinned values — the single source of truth

Both `train.py` and `baseline.py` read these numbers from here. A divergence
between the two scripts would surface as a metric disagreement and be
misdiagnosed as a tracking or data fault — it is the one cause the comparison
cannot tell apart from a real failure, which is why the values live in one place
rather than in each script.

| Parameter | Value |
| --- | --- |
| `estimator` | `DecisionTreeClassifier` |
| `random_state` | 42 |
| `max_depth` | **4** |
| `train_rows` / `test_rows` | 1500 / 500, positional |
| Generator seed | 42 |

`max_depth: 4` is chosen so that accuracy lands clear of both degenerate ends —
neither 1.0, which would make the comparison undiscriminating, nor near chance.

**Validation**: written before submission; the file's own timestamp is the
evidence of ordering. A baseline computed after the job is not a baseline, it is
a rationalisation.

**How it could look right and be wrong**: computed against a different file than
the one uploaded. Guarded by carrying `dataset_sha256` inside the baseline and
requiring it to match the job's reported digest.

---

## 3. Training run

The record the job produces. Must survive the compute node that created it
(FR-012).

| Element | Content |
| --- | --- |
| Parameters | Seed, `max_depth`, estimator name, split sizes, dataset digest |
| Metrics | Accuracy and F1 on the test split, matching the baseline's definitions |
| Tags / banner | Resolved MLflow tracking URI, and versions of `mlflow`, `azureml-mlflow`, scikit-learn, NumPy, pandas |
| Data provenance | Mount path and content digest of the bytes actually read |
| Artifact | The fitted model in MLflow format |

**Validation**:

- The resolved tracking URI is `azureml`-backed. Asserted by the script, which
  exits non-zero otherwise ([research.md § R1](./research.md)).
- The run is readable from the workspace **after** the node is released — that
  is the check, not that it appeared while the job was running.
- Metrics agree with the baseline within `1e-9`; the prediction vector matches
  **exactly**.

**How it could look right and be wrong**: three ways, and all three have bitten
this repository or a project like it.

1. MLflow falls back to a local `mlruns/` directory on the node. The job
   succeeds, exits zero, and every metric is destroyed at scale-down. Guarded by
   the assertion.
2. Metrics are written but are not the metrics claimed — trained on the wrong
   column, or computed on the training split rather than the test split. Guarded
   by the baseline comparison, which is the only check that can disagree.
3. The run exists but the artifact is a file rather than a loadable model.
   Guarded by entity 4.

---

## 4. Model artifact

The fitted estimator, logged in MLflow format so that Phase 2 can deploy it
without a scoring script ([research.md § R8](./research.md)).

**Validation** — all three required, because each catches a different failure:

1. Retrieved from the run **after** the node has been released.
2. Loads in the pinned local environment.
3. Reproduces the baseline's prediction vector exactly, on the same inputs.

**How it could look right and be wrong**: an artifact listed against the run
proves an upload happened. It does not prove the bytes are a model, that the
model is the one that was trained, or that it can be loaded. Only step 3
distinguishes those.

---

## 5. Registered model

| Field | Notes |
| --- | --- |
| Name | Stable across versions |
| Version | Assigned by the registry, not chosen |
| Type | MLflow model — the property that enables no-code batch deployment |
| Source run | Reference back to the run that produced it |

**Validation**: registering a second time yields a **distinct higher version**,
and the earlier version remains retrievable (FR-018).

**How it could look right and be wrong**: an entry whose version field reads `1`
proves a field exists. It does not prove the registry versions. The second
registration is free — registration is metadata over an artifact that already
exists — which is exactly why there is no excuse for asserting this instead of
demonstrating it.

---

## 6. Scoring input and output

| Artifact | Content |
| --- | --- |
| Input | Rows drawn from the test split, **with correct predictions that differ** (FR-022) |
| Output | One prediction per input row, joined back to the input by row order |

**Validation**: predictions match, row for row, those computed locally from the
**same registered version** — not from the locally trained model, which would be
comparing the baseline against itself.

**How it could look right and be wrong**: two ways.

- If every input row had the same correct class, a deployment that returned a
  constant would pass. FR-022 forbids that input set.
- If the comparison used the local baseline's model rather than the downloaded
  registered version, it would verify that scikit-learn is deterministic —
  something already known — rather than that the endpoint served the registered
  model.

---

## Entity relationships

```text
generator (seed=42)
      │
      ▼
training dataset ──uploaded──► container ──addressed by──► data store
      │                                                        │
      │ same bytes                                             │ ro_mount
      ▼                                                        ▼
local baseline ◄────── compared against ──────────────── training run
  (before)                                                     │
      │                                                        │ logs
      │                                                        ▼
      │                                                  model artifact
      │                                                        │ registered
      │                                                        ▼
      │                                                 registered model
      │                                                        │ deployed
      │                                                        ▼
      └──── predictions compared, row for row ──────► batch scoring output
```

The diagram makes the feature's one structural claim visible: **every arrow that
produces something is matched by an arrow that checks it against something
computed independently.** Where a step has no such matching arrow, it is not
verified — it is merely done.
