# Training pipeline — from a job that runs to a model that answers

Feature 005, Phase 1. A training job that runs on the compute cluster built in
feature 004, reads its data through the credential-less data store, tracks
parameters and metrics with MLflow, and produces a model artifact in MLflow
format for Phase 2 to register and serve.

**Phase 2 — registry and batch endpoint — is not built yet.**

## What is here

| File | Role |
| --- | --- |
| `generate_data.py` | Writes the synthetic dataset from a pinned seed |
| `pinned.py` | The hyperparameters and the split, in one place |
| `modelling.py` | Load, split, fit, score — shared by both sides |
| `baseline.py` | Computes the baseline locally, **before** the job |
| `train.py` | The job: probes, asserts, trains, tracks, saves |
| `train-job.yml` | The workload definition |
| `compare.py` | Compares the tracked run against the baseline |
| `.amlignore` | Keeps `.venv`, the dataset and the baseline out of the snapshot |

`data/`, `baseline.json` and `downloaded-model/` are generated and untracked.
Rebuild them with:

```bash
uv sync
uv run python generate_data.py     # writes data/training.csv
uv run python baseline.py          # writes baseline.json
```

Both are deterministic: the CSV was regenerated and compared byte for byte
against the first copy before anything was uploaded.

## The question this phase existed to answer

**Does the Azure ML workspace configure MLflow tracking itself, or must the job
declare it?**

**It configures it.** `MLFLOW_TRACKING_URI` is injected into the job container
and `mlflow.get_tracking_uri()` resolves to the same `azureml://` value naming
the workspace. The job declares nothing.

That answer was worth spending a job on rather than reading, because the failure
mode is silent: unconfigured MLflow does not raise. It writes to a local
`mlruns/` directory on the compute node, the script exits zero, and every metric
is destroyed when the node is released. `train.py` therefore refuses to train —
exit code **3** — unless the resolved URI is `azureml`-backed. Running the same
script locally exits 3 with `file:///…/mlruns`, which is how the check was
watched failing before it was trusted passing.

## Observed values

| | Value |
| --- | --- |
| Successful job | `placid_knot_z03v76ysql` |
| Dataset `sha256` | `9130b02593b6ce3fe84bbef7543b9397b96e05e36d131afa4b8daaf84bb60384` |
| `accuracy` | `0.854` |
| `f1` | `0.8488612836438924` |
| Prediction digest | `495d5e534a0df9dcdcf499d09206b14e0398748b92068f32d542bfb0178f0163` |

The prediction vector computed on macOS and the one computed on the Ubuntu node
are **identical, all 500 of them** — which is what a decision tree buys and a
`LogisticRegression` would not have: tree fitting is comparison and counting, so
it never routes through BLAS and never inherits the difference between Apple's
Accelerate and OpenBLAS.

## One thing that will bite anyone reusing this

The curated environment `sklearn-1.5:52` ships **MLflow 3.13.0**, and
`mlflow.sklearn.log_model` fails against Azure ML on it:

```
API request to endpoint /api/2.0/mlflow/logged-models failed with error code 404
```

MLflow 3 routes model logging through the LoggedModel API, which the Azure ML
tracking server does not implement. It is **not** an authorization problem — the
same run wrote params, metrics and tags to the workspace without complaint.

`train.py` writes the model to `./outputs/`, which Azure ML uploads on its own
with no MLflow API in the path, and additionally calls `mlflow.log_artifacts`,
reporting the outcome in the log rather than assuming it. Both mechanisms work,
so the run carries the model at `model/` and at `outputs/model/`.

## Running it

```bash
# free, local
uv run python generate_data.py
uv run python baseline.py

# billable: allocates a cluster node
az storage blob upload --account-name <account> --account-key "$KEY" \
  --container-name training-data --name training.csv \
  --file data/training.csv --overwrite --auth-mode key
az ml job create -g rg-ai300-test01 -w <workspace> -f train-job.yml --stream

# free: the criterion
uv run python compare.py --run-log std_log.txt \
  --run-id <job-name> --tracking-uri "<azureml tracking uri>"
```

Job logs are read from blob storage with the account key, not with
`az ml job download`, which fails with `AuthorizationPermissionMismatch` on this
workspace — the author holds no data-plane role, established in feature 004.

**Cost**: two activations cost ≈0.04–0.09 € depending on the load-balancer tail.
Billed node time ran **2.2–2.3× the script time**, because billing starts when
the node is allocated and not when the script starts. Prefer fewer, longer jobs.
