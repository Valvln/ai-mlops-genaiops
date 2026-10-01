# Training jobs, notebooks and pipelines

**Status: command jobs built and measured; no pipeline, no notebook.** Feature
004 ran a verification job and feature 005 a training job, both command jobs on
the cluster, submitted with `az ml job create`. Training never went through a
notebook or a pipeline. Both are declared gaps in the tracker.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Use notebooks for experimentation and
exploration*, *Run model training scripts*, *Implement training pipelines*.
Distributed training is in `distributed-training.md`, sweeps in
`hyperparameter-sweep.md`, AutoML in `automl.md`.

---

## 1. Command jobs

A command job is code plus a command plus an environment plus a compute
target. Inputs and outputs are referenced in the command as
`${{inputs.<name>}}` and `${{outputs.<name>}}`.

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
code: src
command: python main.py --data ${{inputs.training_data}}
environment: azureml:AzureML-lightgbm-3.3@latest
compute: azureml:cpu-cluster     # delete the line to use serverless compute
experiment_name: my-experiment
display_name: my-run
inputs:
  training_data:
    type: uri_file
    path: azureml://datastores/<ds>/paths/<file>
```

- `code` is uploaded to the workspace at submission. Git metadata is attached
  if the folder is a repository (`aml-github-actions-and-git.md` § 2).
- Status moves **Starting → Preparing → Running → Completed**. `az ml job stream`
  or `ml_client.jobs.stream()` follows the log.
- Register the output model with the job's `name` in the path
  (`mlflow-tracking-and-model-registry.md` § 3).
- Jobs **don't support container registries with a customized domain name
  label**. Use the default `<name>.azurecr.io` form.

### Learn's troubleshooting table for job submission

| Error | Cause |
| --- | --- |
| `ComputeNotFound` | cluster name mismatch, or cluster deleted |
| `EnvironmentNotFound` | curated environment deprecated or unavailable |
| `QuotaExceeded` | not enough vCPU quota for the VM size |
| `DefaultAzureCredential failed` | not signed in |

---

## 2. Notebooks

- Running cells needs a **compute instance**. Editing doesn't. A stopped
  instance starts on the first cell run.
- Notebooks are **autosaved every 30 seconds** into the `.ipynb`. Checkpoints are
  separate and created on *Save and checkpoint* or by name.
- Compute instances are personal. A shared notebook runs on **each user's own**
  instance. User files live on the workspace file share and are shared across
  that user's instances.
- Learn recommends VS Code for the Web or VS Code Desktop connected to the
  instance.
- Experiment tracking from a notebook uses `mlflow.set_experiment()` and
  `mlflow.start_run()`, ended with `mlflow.end_run()` or a context manager.

---

## 3. Pipelines

A pipeline splits a task into steps, each normally a **component**
(`aml-environments-components-registries.md` § 2). Benefits Learn names:
teams own separate steps, **unchanged steps are reused**, each step runs on the
compute that suits it.

```yaml
type: pipeline
settings:
  default_compute: azureml:cpu-cluster   # or azureml:serverless
jobs:
  prep:
    type: command
    component: azureml:prep_data:1
  train:
    type: command
    component: azureml:train_model:2
    inputs:
      data: ${{parent.jobs.prep.outputs.clean}}
```

- `type: pipeline` is required. `jobs` holds the child jobs. The CLI pipeline
  page lists **`command` and `sweep`** as the supported child types. The
  AutoML page shows AutoML steps inside pipelines.
- `default_compute` applies to every step; **a step's own `compute` wins**.
- **Reuse:** a component with `is_deterministic: true` (the default) reuses the
  previous result when its inputs haven't changed. Set `false` to force a rerun.
- Literal inputs with `min`/`max` fail **at validation**, before submission.
- The same data syntax serves command, sweep and pipeline jobs.
- Pipelines are authored in YAML (CLI), Python (SDK v2) or the Designer UI.

### Which pipeline product

| Scenario | Azure product |
| --- | --- |
| model orchestration, data to model | **Azure ML pipelines** |
| data orchestration, data to data | Azure Data Factory |
| code and app orchestration, CI/CD with approvals | Azure Pipelines |

---

## 4. Comparing jobs

- MLflow: `search_runs` across experiments, `get_metric_history` for curves
  (`mlflow-tracking-and-model-registry.md` § 2).
- Studio: the experiment's Metrics tab charts selected runs; a preview panel
  compares parameters, metrics and tags of selected jobs and models.
- Sweep jobs add parallel coordinates and scatter charts across trials.

---

## 5. What this repository measured, and what it did not

**Measured** (`specs/004-…`, `specs/005-…`, `mlops/training-pipeline/`):

- **One submission does all the work.** `train-job.yml` probes the environment,
  trains, logs and saves the model in one job, because each job pays a node
  activation from cold.
- **The job checks its own input.** The expected SHA-256 of the training file is
  passed in the command, so a wrong file fails the job.
- **Comparison by predictions.** The model from the cluster and the model trained
  locally produced identical predictions on 500 cases. That was the success
  criterion.
- **Five failed batch invocations, five different causes,** four of them in the
  image build before any node was allocated.

**Not measured:** a notebook on a compute instance, a pipeline, component
reuse, serverless compute, the studio comparison panel.

---

## 6. What this note would cost to verify

A two-step pipeline from registered components on the existing cluster costs
two activations at most, about 0.10 €, less if the second step lands on a warm
node. Running it twice unchanged tests reuse at the cost of nothing new.

---

## Sources

- [Train models with Azure Machine Learning CLI, SDK, and REST API](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-model): read 2026-10-01 (ms.date 2026-05-20); § 1
- [Run Jupyter notebooks in your workspace](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-run-jupyter-notebooks): read 2026-10-01 (ms.date 2026-08-21); § 2
- [Track experiments and models by using MLflow](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs): read 2026-10-01 (ms.date 2025-10-17); § 2 notebook tracking
- [What are Azure Machine Learning pipelines?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines): read 2026-10-01 (ms.date 2026-09-09); § 3
- [Create and run component-based ML pipelines with the CLI](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-component-pipelines-cli): read 2026-10-01 (ms.date 2026-08-31); § 3
- [Query and compare experiments and runs with MLflow](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-track-experiments-mlflow): read 2026-10-01 (ms.date 2025-11-13); § 4
- `specs/004-datastore-compute-cluster/`, `specs/005-training-job-batch-endpoint/`, `mlops/training-pipeline/`: § 5
