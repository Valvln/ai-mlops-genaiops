# MLflow tracking and the model registry

**Status: built and measured.** Feature 005 trained a decision tree in a
command job, tracked parameters and metrics with MLflow, and registered the
model three times. The batch deployment names version 1 explicitly. Learn's
model lifecycle features beyond that (stages, archive, registries) were not
used.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Configure experiment tracking with
MLflow*, *Compare model performance across jobs*, *Register an MLflow model*,
*Manage model lifecycle, including archiving models*.

---

## 1. Tracking

An Azure ML workspace is **MLflow-compatible**: it acts as the tracking server
and Azure ML hosts no MLflow server instance. **SDK v2 has no logging API of its
own.** Learn's direction is to log with MLflow, which keeps training code
portable.

| Where the code runs | What you configure |
| --- | --- |
| an Azure ML **job** | nothing: the tracking URI is set for the job. Set the experiment with the job's `experiment_name`, the run name with `display_name` |
| a notebook, a local machine, another cloud | `mlflow` plus the `azureml-mlflow` plugin, and the workspace tracking URI |

Rules for jobs:

- Don't call `mlflow.start_run(run_name=...)` in a job: name the run with the
  job's `display_name`. `mlflow.start_run()` without a name reuses the active
  run.
- All **curated environments** include MLflow. A custom environment must list
  `mlflow` and `azureml-mlflow`.
- `mlflow-skinny` is enough for tracking and logging.
- Without an `experiment_name`, a sweep job defaults it to the name of the
  working directory. Interactive runs go to an experiment named `Default`.
- `mlflow.autolog()` logs what each supported framework defines.

Language limits: **R** tracks metrics, parameters and models in jobs only, with
no model registration through MLflow. **Java** tracks metrics and parameters
only.

**MLflow Projects (`MLproject`) support retires in September 2026.** Learn moves
those users to Azure ML jobs.

---

## 2. Querying and comparing runs

`mlflow.search_runs()` returns a pandas DataFrame with `params.*` and
`metrics.*` columns.

- A metric logged many times returns **only its last value** here. All values
  need `MlflowClient().get_metric_history()`.
- Without `experiment_ids`, `experiment_names` or `search_all_experiments=True`,
  the search covers **only the active experiment**.
- `filter_string` supports **AND, not OR**. Parameters support `=`, `!=` and
  `LIKE`.
- **`order_by` on `metrics.*`, `params.*` or `tags.*` isn't supported** in Azure
  ML. Sort the DataFrame with pandas.
- `attributes.duration` exists in Azure ML only.
- **Renaming experiments isn't supported.**
- Child runs (sweeps, pipelines) carry the tag `mlflow.parentRunId`.

| Azure ML job status | MLflow `attributes.status` |
| --- | --- |
| Not started, Queued, Preparing | `Scheduled` |
| Running | `Running` |
| Completed | `Finished` |
| Failed | `Failed` |
| Canceled | `Killed` |

Studio has a preview panel to compare parameters, metrics and tags across
selected jobs and models.

---

## 3. Registering a model

| Source | Path syntax | Lineage to the job |
| --- | --- | --- |
| MLflow run artifact | `runs:/<run-id>/<path>` | yes |
| job output | `azureml://jobs/<job>/outputs/<output>/paths/<path>` | yes |
| default artifact location of a job | `azureml://jobs/<job>/outputs/artifacts/paths/<path>` | yes, same as `runs:/` |
| datastore | `azureml://datastores/<ds>/paths/<path>` | no |
| local folder | `./model` | no |

- Model **types**: `mlflow_model`, `custom_model`, `triton_model`. Models
  registered with v1 are `custom`.
- An MLflow model folder holds `MLmodel`, the model file, `conda.yaml` and
  `requirements.txt`.
- MLflow registration from a run works **only in the workspace where the run was
  tracked**. Cross-workspace operations go through **registries**.
- `az ml model create --path` requires `--name` and `--version`. Version
  auto-increment is on the `--file` path, where `version` can be omitted
  (simulation 03 Q2).

---

## 4. Lifecycle: update, archive, delete, stages

| Operation | Azure ML |
| --- | --- |
| edit description, tags | ✓ |
| change anything else | **no**: create a new version |
| rename a model | **no**: models are immutable |
| delete one version | ✓ |
| delete the model container | **no**: delete every version |
| archive | ✓, all versions or one |

**Archive** hides a model from `az ml model list`. **It stays usable** in
workflows. A new version created under an archived name is archived too.

### MLflow stages

- Visible and usable **only through the MLflow SDK**. Studio, the Azure ML CLI,
  the Azure ML SDK and REST **can't see them**.
- **Deployment from a stage isn't supported.** Deploy by version.
- Stage names are case sensitive. Several versions can share a stage; loading
  `models:/<name>/<stage>` returns the most recent of them.
- A transition leaves other versions in that stage unchanged, unless
  `archive_existing_versions=True`.

### Loading

`models:/<name>/latest`, `models:/<name>/<version>`, `models:/<name>/<stage>`.
`mlflow.<flavor>.load_model()` returns the native object;
`mlflow.pyfunc.load_model()` returns the generic interface.

---

## 5. What this repository measured, and what it did not

**Measured** (`specs/005-training-job-batch-endpoint/results.md`,
`mlops/training-pipeline/train.py`):

- **The job set the tracking URI itself.** `MLFLOW_TRACKING_URI` was injected
  into the container. `train.py` still refuses to train if the resolved URI is a
  local `file://…/mlruns`, because that is how a job exits 0 with its metrics
  lost. This matches § 1.
- **`mlflow.sklearn.log_model` failed with `404` on
  `/api/2.0/mlflow/logged-models`.** The curated environment shipped MLflow
  3.13; its LoggedModel API isn't implemented by the Azure ML tracking server.
  Parameters, metrics and tags from the same run had been written. The pages
  read here say nothing about MLflow 3. The workaround: `mlflow.sklearn.save_model`
  to `./outputs/model`, uploaded by the job.
- **Registered from the run, lineage kept.** Versions 1 and 2 carry `job_name`;
  version 3, registered from a datastore path, has `job_name: null`. This is the
  lineage column of § 3, observed.
- **Registering identical bytes again produced a new version** and left version
  1 retrievable.
- **Deployment pins version 1**, never `latest`.

**Not measured:** stages, archive, model share to a registry, `search_runs`
comparisons (the comparison done here was of predictions, not of runs).

---

## 6. What this note would cost to verify

Stages, archive and queries are metadata operations: no compute. They need a
workspace, so the container registry's daily rate.

---

## Sources

- [MLflow and Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow): read 2026-10-01 (ms.date 2025-10-06); § 1, MLflow Projects retirement
- [Track experiments and models by using MLflow](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs): read 2026-10-01 (ms.date 2025-10-17); § 1
- [Query and compare experiments and runs with MLflow](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-track-experiments-mlflow): read 2026-10-01 (ms.date 2025-11-13); § 2
- [Manage models registry in Azure Machine Learning with MLflow](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow): read 2026-10-01 (ms.date 2025-11-13); §§ 3–4
- [Work with registered models in Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models): read 2026-10-01 (ms.date 2026-01-27); §§ 3–4
- [az ml model](https://learn.microsoft.com/en-us/cli/azure/ml/model): read 2026-10-01 (ms.date 2026-09-01); `--path` requires `--name` and `--version`
- [CLI (v2) sweep job YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-sweep): read 2026-10-01 (ms.date 2024-12-03); default `experiment_name`
- `specs/005-training-job-batch-endpoint/results.md`, `mlops/training-pipeline/train.py`: § 5
