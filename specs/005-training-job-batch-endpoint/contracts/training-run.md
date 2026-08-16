# Contract: what the training job must emit, and what checks it

**Feature**: 005 · Phase 1

The job's log is the interface. Everything the verification needs must be
greppable from it, because the alternative — reading it back through a UI — is
neither reproducible nor available to a script, and because on this workspace the
author cannot download job logs from the CLI at all (feature 004: no data-plane
role; logs are read with the account key).

The prefixes below are chosen so that a single pass over `std_log.txt` yields
every value the comparison needs.

---

## 1. The environment banner — emitted before anything else

Settles [research.md § R1 and § R2](../research.md) at no extra cost.

```text
ENV-PROBE-BEGIN
ENV-PROBE mlflow_tracking_uri_env=<value of MLFLOW_TRACKING_URI, or ABSENT>
ENV-PROBE mlflow_resolved_uri=<mlflow.get_tracking_uri()>
ENV-PROBE mlflow_version=<version>
ENV-PROBE azureml_mlflow_version=<version, or ABSENT>
ENV-PROBE sklearn_version=<version>
ENV-PROBE numpy_version=<version>
ENV-PROBE pandas_version=<version>
ENV-PROBE-END
```

**The assertion that follows it is the load-bearing part.** If
`mlflow_resolved_uri` is not `azureml`-backed, the script MUST exit non-zero with
a named error and MUST NOT train.

Rationale: MLflow does not fail when unconfigured. It writes to a local `mlruns/`
directory on the node, the job exits zero, and the metrics are destroyed at
scale-down. Without this assertion the feature's most likely failure is a green
run that tracked nothing — the exact shape of defect this repository keeps
producing.

**Both outcomes are acceptable results.** If the URI is present, the prediction
in R1 is confirmed and the answer is "the workspace configures it". If it is
absent, the job declares it explicitly and is resubmitted, and the answer is "the
job must declare it". What is *not* acceptable is not knowing.

---

## 2. Data provenance — emitted after the mount, before training

```text
DATA-PROBE-BEGIN
DATA-PROBE path=<mount path the input arrived at>
DATA-PROBE bytes=<byte count>
DATA-PROBE sha256=<digest of the bytes read>
DATA-PROBE rows=<data rows, excluding header>
DATA-PROBE train_rows=<count>
DATA-PROBE test_rows=<count>
DATA-PROBE-END
```

`sha256` MUST equal the digest recorded locally before the upload. This is what
prevents the whole verification from passing on data the job supplied to itself
(FR-004), and it reuses feature 004's mechanism unchanged — that job proved a
read with a checksum for the same reason.

---

## 3. What is tracked to the run

| Kind | Key | Notes |
| --- | --- | --- |
| Param | `seed` | 42 |
| Param | `estimator` | `DecisionTreeClassifier` |
| Param | `max_depth` | Fixed, stated in the job definition |
| Param | `train_rows`, `test_rows` | 1500 / 500 |
| Param | `dataset_sha256` | Ties the run to the exact bytes |
| Metric | `accuracy` | Test split |
| Metric | `f1` | Test split |
| Artifact | model | MLflow format — required for no-code batch deployment |

Metrics are computed on the **test split only**. Computing them on the training
split is a failure mode that yields plausible numbers and would be caught by the
baseline comparison, which is the point of having one.

---

## 4. Metrics echoed to the log

```text
METRIC-BEGIN
METRIC accuracy=<value, full precision>
METRIC f1=<value, full precision>
METRIC predictions_sha256=<digest of the test-split prediction vector>
METRIC-END
```

Duplicated into the log deliberately. It gives the comparison a path that does
not depend on the tracking store being readable, which matters on the one run
where the thing under test is whether the tracking store is reachable at all.

Full precision, not rounded — a rounded value cannot be compared at `1e-9`.

---

## 5. The comparison, which is the actual criterion

`compare.py` reads the recorded baseline and the tracked run, and exits non-zero
on any disagreement.

| Compared | Rule |
| --- | --- |
| `dataset_sha256` | **Exact.** Baseline and run trained on the same bytes |
| Prediction vector digest | **Exact.** Chosen so this is achievable — see [research.md § R4](../research.md) |
| `accuracy`, `f1` | Absolute difference ≤ `1e-9` |
| Parameters | Exact, key by key |

**The tolerance is not a negotiating position.** FR-016: a disagreement beyond it
is recorded and investigated, never absorbed by widening it. The estimator was
chosen specifically so that exact agreement is expected; a loose tolerance would
throw away the discriminating power that choice bought.

**Order matters.** The baseline is written to disk before the job is submitted.
A comparison against a baseline produced afterwards proves only that the same
code run twice agrees with itself.

---

## 6. Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Trained, tracked, and every probe satisfied |
| 2 | Input not mounted, or mounted as the wrong type |
| 3 | Tracking URI is not `azureml`-backed — refused to train |
| 4 | Data digest disagrees with the expected value passed to the job |

Distinct codes so a failed run is diagnosable from the log without a
resubmission. Because billing runs from allocation, a resubmission to find out
*why* costs roughly a full job ([research.md § R10](../research.md)) — which is
why the script is required to log everything a diagnosis needs on its first run
(FR-026).
