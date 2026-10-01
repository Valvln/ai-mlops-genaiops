# Batch endpoints and batch deployments

**Status: built, deployed, never answered.** Feature 005 created
`ai300-batch-dt` with the deployment `dt-scored`, model version 1, on the
training cluster. Five invocations failed with five different causes. The
teardown of 2026-08-18 removed it. SC-011 (a successful batch answer) stays
open. The YAML is in `mlops/training-pipeline/`.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Deploy models as real-time or batch
endpoints with managed inference options*, *Test and troubleshoot model
endpoints*. Online endpoints are in `online-endpoints.md`.

---

## 1. When batch

Learn's criteria: expensive models, large inputs spread over many files, **no
low-latency requirement**, inputs already in storage or a data asset,
parallelism available. Outputs go to storage. Invocation is **asynchronous**:
it creates a batch job.

| | Online endpoint | Batch endpoint |
| --- | --- | --- |
| Routing across deployments | traffic split, mirroring | **default deployment** only |
| Authentication | key, `aml_token`, `aad_token` | **Microsoft Entra ID only** |
| Scale to zero | no | **yes** |
| Overcapacity | throttling | **queuing** |
| Cost basis | per deployment, instances running | **per job**: instances consumed by the job, capped at the cluster maximum |
| Local testing | yes | no |
| Low-priority compute | no | yes |

> "Azure Machine Learning doesn't charge you for batch endpoints or batch
> deployments themselves." Queued jobs consume nothing.

Two deployment types: **model deployment** and **pipeline component
deployment** (a whole inference pipeline).

---

## 2. A model deployment

| Element | Rule |
| --- | --- |
| model | **must be registered in the workspace** |
| compute | a compute cluster or Kubernetes, shared freely between deployments and jobs |
| scoring script | `init()` once per process; `run(mini_batch)` gets a **list of file paths** and returns a DataFrame or array, one element per successful input. **Optional for MLflow models** |
| environment | **optional for MLflow models**. Must include `azureml-core` and `azureml-dataset-runtime[fuse]`. **Curated environments aren't supported** |

- **AutoML's scoring script works only for online endpoints.**
- The endpoint name is unique **per region**, because it is in the URI.
- `--set-default` makes a new deployment the default at creation. Learn's
  production advice: create it **without** default, test it by invoking that
  deployment by name, then switch the default.

### Settings (`settings:` block from CLI 1.7)

| Setting | Default | Meaning |
| --- | --- | --- |
| `resources.instance_count` | 1 | nodes per job |
| `max_concurrency_per_instance` | 1 | parallel `run()` calls per node |
| `mini_batch_size` | 10 | **files** per `run()` call |
| `retry_settings.max_retries` | **3** | retries of a failed or timed-out mini-batch |
| `retry_settings.timeout` | **30** s | timeout for one mini-batch |
| `error_threshold` | **-1** | see below |
| `output_action` | `append_row` | see below |
| `output_file_name` | `predictions.csv` | |
| `logging_level` | `info` | `warning`, `info`, `debug` |

Without `type: model` and a `settings:` block, the older root-level layout is
still accepted for compatibility.

### `error_threshold`

> "The number of file failures that should be ignored. If the error count for
> the entire input goes above this value, the batch scoring job is terminated.
> `error_threshold` is for the entire input and not for individual mini
> batches. If omitted, any number of file failures is allowed."

- Unit: **failed files, counted over the whole input**.
- **`-1`** is the default and allows any number of failures.
- **`0`** terminates the job at the first failed file. A positive `n` tolerates
  up to `n`.
- `retry_settings` act first, per mini-batch.

### `output_action`

- **`append_row`**: `run()` **returns** predictions; they are merged into
  `output_file_name`.
- **`summary_only`**: the script **writes its own output files**; nothing is
  merged, only `error_threshold` is evaluated.

### Parallelism

Work is split **by file**: 100 files with `mini_batch_size: 10` give 10
mini-batches, whatever the file sizes. Learn's advice for very large files is to
split them. Skewed file sizes aren't balanced.

---

## 3. Invoking a job

```bash
az ml batch-endpoint invoke --name <endpoint> \
  --input azureml://datastores/<ds>/paths/<folder> \
  --deployment-name <name>           # optional; otherwise the default
  --mini-batch-size 20 --instance-count 5
```

- **Per-job overrides** without changing the deployment: instance count,
  mini-batch size, max retries, timeout, **error threshold**, output location
  and output file name.
- Outputs go by default to the workspace's default blob store, in a folder
  named after the job. **An existing output file fails the job**: use a unique
  location. **Outputs must be on a Blob-based datastore.**
- A pipeline component deployment takes a dictionary of `inputs`; a model
  deployment takes one `input`.
- From a private-link workspace, studio can't invoke a batch endpoint. Use the
  CLI.
- Low-priority VMs were retired on 2026-03-31; they are now Spot. Batch
  endpoints reschedule mini-batches from evicted nodes and keep completed ones,
  with no job-level checkpoint.

---

## 4. Identity: who invokes, who mounts, who reads

- Every invocation needs a **Microsoft Entra token**, user or service principal
  or managed identity. Keys don't exist for batch endpoints.
- The token audience is **`https://ml.azure.com`** for invoking. Managing the
  endpoint uses `https://management.azure.com`.
- **The batch job runs under the identity that invoked it.** That identity needs
  to read the endpoint and deployment, create jobs and experiments, read and
  write datastores, and list datastore secrets.
- A managed identity used to invoke belongs to the **caller**. The batch
  endpoint has no identity of its own.

Who reads the input data:

| Input | Credential in the datastore | Credentials used |
| --- | --- | --- |
| datastore or data asset | yes | the datastore's stored credential |
| datastore or data asset | no | **identity of the job + managed identity of the compute cluster** |
| Blob, ADLS Gen1, ADLS Gen2 path | n/a | **identity of the job + managed identity of the compute cluster** |

> "The managed identity of the compute cluster is used for mounting and
> configuring storage accounts. However, the identity of the job is still used
> to read the underlying data."

So a credential-less input needs **both**: Storage Blob Data Reader for the
**cluster's** identity (mount) and read access for the **invoker** (read).

---

## 5. What this repository measured, and what it did not

**Measured** (`specs/005-training-job-batch-endpoint/results.md`,
`mlops/training-pipeline/`):

- **Idle cost zero.** The endpoint with one provisioned deployment billed
  nothing while idle. This matches § 1.
- **The endpoint has no identity** (`identity: null`, `authMode: AADToken`).
  The model mount was refused for the cluster's identity until it got Storage
  Blob Data Reader on the `azureml` container. This matches § 4 for the
  **mount**.
- **The read half of § 4 was never isolated.** The repository invoked as the
  author, who already had data access, so a missing grant for the invoker could
  not show. The repository's earlier wording, "the cluster's identity performs
  the read", is incomplete against § 4.
- **Curated environment refused**, MLflow no-code path broken by a pyarrow
  conflict, custom scoring environment built instead
  (`aml-environments-components-registries.md` § 4).
- **`error_threshold: -1` was commented as "no failure tolerance"** for two
  features. Corrected to `0` on 2026-08-18, from the reference. Not re-verified
  against a live deployment.
- **`append_row` is correct here**: `scoring.py` returns a DataFrame.

**Not measured:** a successful batch answer (SC-011), per-job overrides, a
pipeline component deployment, Spot nodes.

---

## 6. What this note would cost to verify

Recreating the endpoint and deployment costs nothing at rest. One invocation
over a small folder on `Standard_DS1_v2` is one node activation, about 0.05 €,
plus the custom environment build if its image isn't cached, about 0.28 € an
hour of build time. Invoking once as a service principal without data access
would test the read half of § 4.

---

## Sources

- [Batch endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-batch): read 2026-10-01 (ms.date 2026-08-25); §§ 1, 3, 4
- [Endpoints for inference in production](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints): read 2026-10-01 (ms.date 2026-08-21); § 1 comparison
- [Deploy models for scoring in batch endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-batch-model-deployments): read 2026-10-01 (ms.date 2026-08-21); §§ 2–3
- [CLI (v2) batch deployment YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-deployment-batch): read 2026-10-01 (ms.date 2023-11-15); § 2 settings, `error_threshold`, `output_action`
- [Authorization on batch endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-authenticate-batch-endpoint): read 2026-10-01 (ms.date 2026-03-23); § 4
- [Create jobs and input data for batch endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-access-data-batch-endpoints-jobs): read 2026-10-01 (ms.date 2026-01-13); § 4
- `specs/005-training-job-batch-endpoint/results.md`, `mlops/training-pipeline/batch-deployment.yml`: § 5
