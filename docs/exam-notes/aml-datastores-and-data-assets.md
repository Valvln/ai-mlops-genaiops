# Datastores and data assets

**Status: one identity-based datastore built and measured.** `infra/main.bicep`
declares `ai300_training_data`, a Blob datastore with `credentialsType: None`.
Feature 004 proved a cluster node could read a known file through it, by
checksum. Feature 005 trained from it. No data asset was ever registered: jobs
used datastore URIs directly.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Create and manage datastores*, *Create
and manage data assets*. Which identity reads the data is in
`aml-identity-and-access.md` § 4.

---

## 1. Datastores

A datastore is a **reference** to an existing storage service. It creates no
storage. It stores connection information, and for credential-based access it
keeps the secret out of your scripts.

### Storage types and authentication

| Storage | Credential-based | Identity-based |
| --- | --- | --- |
| Azure Blob container | account key, SAS | ✓ |
| Azure File share | account key, SAS | **✗** |
| Azure Data Lake Storage Gen2 | service principal | ✓ |
| Azure Data Lake Storage Gen1 | service principal | ✓ (retired 2024-02-29, reference only) |
| OneLake (Fabric), preview | service principal | ✓ |

**An Azure Files datastore can't be identity-based.** It needs an account key or
a SAS token.

- **Credential-based:** the secret is cached in the workspace's Key Vault.
  Learn's warning: other workspace users with enough permission can retrieve
  it. Retrieving it needs
  `Microsoft.MachineLearningServices/workspaces/datastores/listsecrets/action`,
  which Contributor, Azure AI Developer and AzureML Data Scientist carry.
- **Identity-based:** nothing is stored. Access is decided by Azure RBAC on the
  storage account, for the identity that performs the read. Minimum role to
  read: **Storage Blob Data Reader**.
- If a datastore **has** cached credentials, those credentials are used, even
  for a job set to user identity.

### Default datastores

| Name | Type | Holds |
| --- | --- | --- |
| `workspaceblobstore` | Blob, `azureml-blobstore-{workspace-id}` | data uploads, job code snapshots, pipeline data cache; the default |
| `workspaceworkingdirectory` | File share | notebooks, compute instance files |
| `workspacefilestore` | File share | alternative upload location |
| `workspaceartifactstore` | Blob, `azureml` | metrics, models, components |

### URIs

```
azureml://datastores/<datastore>/paths/<path>
wasbs://<container>@<account>.blob.core.windows.net/<path>
abfss://<filesystem>@<account>.dfs.core.windows.net/<path>
https://<public-server>/<file>
```

---

## 2. Data in jobs: types and modes

| Type | Points at | Typical use |
| --- | --- | --- |
| `uri_file` | one file | a single CSV |
| `uri_folder` | one folder | Parquet/CSV sets, images |
| `mltable` | a table definition | changing schemas, subsets of large tables, **AutoML tables** |

| Mode | Input | Output |
| --- | --- | --- |
| `ro_mount` | ✓ | |
| `rw_mount` | | ✓ |
| `download` | ✓ | |
| `upload` | | ✓ |
| `direct` | ✓ | |

`eval_mount` and `eval_download` exist only for MLTable: the data runtime
evaluates the MLTable file and mounts the listed paths.

An MLTable file must be named exactly **`MLTable`**. `MLTable.yaml` is not
recognised.

---

## 3. Data assets

A data asset is a named, versioned pointer: `azureml:<name>:<version>`. Creating
it stores a reference and a copy of metadata. **The data stays where it is**, so
there is no extra storage cost.

- **A data asset version is immutable.** It can't be modified or deleted.
- **Deletion is not supported by design.** Learn's reasons: production jobs
  would fail, reproduction would break, lineage would break, audit would have
  gaps.
- A data asset created from a **local path** is uploaded to the default
  datastore.
- A job output with a `name` set creates a data asset.

### Alternatives to deletion

| Problem | Learn's fix |
| --- | --- |
| wrong name, unused, clutters the list | **archive** |
| wrong path | new **version** under the same name |
| wrong **type** | archive it and create a **new name**: a new version can't change the type |

**Archive** hides the asset from `az ml data list` and from studio. Archived
assets **remain usable** in jobs. You can archive all versions or one version.
If all versions are archived, you can't restore a single version; you restore
the whole container. Archiving a single version isn't available in studio.

### Versioning data that grows

Learn's pattern for reproducible versions of growing data is an **MLTable that
lists explicit paths**, for example the weekly folders up to a date. A later
version lists more paths. The earlier version still mounts only the paths its
MLTable declares, so an experiment on it is reproducible.

### Tags and lineage

Tags are key-value metadata, for example `medallion:silver`,
`sensitivity:PII`, `RAI_audit:approved`. Studio shows which jobs consumed a data
asset.

---

## 4. What this repository measured, and what it did not

**Measured** (`specs/004-datastore-compute-cluster/`, `mlops/datastore-check/`):

- **An identity-based Blob datastore works without a key.** The job read a
  known file and printed its byte count and SHA-256. The check was the
  checksum, so a wrong file could not pass.
- **The identity that matters is the one that performs the read.** The cluster's
  system-assigned identity holds Storage Blob Data Reader on the
  `training-data` container, and jobs run with `identity: type: managed`
  (§ 1 and `aml-identity-and-access.md` § 4).
- **`uri_file` with `ro_mount`.** The job YAMLs choose `uri_file` so that a wrong
  path fails at mount time.
- **Empty credentials in a tool's output are not proof of no credentials**
  (`README.md`, feature 002): the tool hid them.

**Not measured:** a registered data asset, archive and restore, MLTable,
credential-based datastores, Azure Files datastores.

---

## 5. What this note would cost to verify

Registering a data asset, archiving it and creating a second version is
metadata work: no compute, a few kilobytes of storage. It needs an existing
workspace, which brings back the container registry's 0.1462 € a day.

---

## Sources

- [Data concepts in Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-data): read 2026-10-01 (ms.date 2025-02-10); §§ 1–2
- [Create datastores](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-datastore): read 2026-10-01 (ms.date 2026-02-03); § 1
- [Data administration](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-administrate-data-authentication): read 2026-10-01 (ms.date 2024-09-06); `listsecrets`, roles
- [Set up authentication between Azure Machine Learning and other services](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-identity-based-service-authentication): read 2026-10-01 (ms.date 2026-01-22); cached credentials, identity-based storage types
- [Create and manage data assets](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-data-assets): read 2026-10-01 (ms.date 2026-08-21); § 3
- `specs/004-datastore-compute-cluster/`, `mlops/datastore-check/`: § 4
