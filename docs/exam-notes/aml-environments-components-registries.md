# Environments, components and registries

**Status: environments built and measured; components and registries not
built.** Training used the curated `sklearn-1.5` environment pinned to version
52. Batch scoring needed a custom environment, `ai300-batch-scoring`, because
the curated one was refused. No component was registered and no registry was
created.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Create and manage environments*,
*Create and manage components*, *Share assets across workspaces by using
registries*.

---

## 1. Environments

### Three kinds

| Kind | Who maintains it | Notes |
| --- | --- | --- |
| **Curated** | Microsoft | hosted in the `azureml` registry, images already cached, patched regularly |
| **User-managed** | you | Docker image (BYOC) or Docker build context; you install every package |
| **System-managed** | Azure ML builds conda on top of a base image | from a conda file plus a base image |

Curated references:
`azureml://registries/azureml/environments/<name>/versions/<n>` or
`.../labels/latest`. In CLI and SDK listings, curated names start with
`AzureML-`. **The prefixes `AzureML-` and `Microsoft` are reserved**: a job
fails if a custom environment name starts with either.

### Creating one

```yaml
# from an image
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
# from conda on top of an image
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: conda.yml
# from a build context (Dockerfile at most 1 MB)
build:
  path: docker-context
```

With a conda file, Azure ML runs the job in the **conda environment it built**.
Packages installed in the base image are not on that path, which causes
runtime failures.

### Build, hash and cache

- An image is built on first use and cached in the **workspace container
  registry**. Without dedicated build compute, the build runs on **workspace
  serverless compute quota**.
- Reuse is decided by a **hash** of: base image, custom Docker steps, Python
  packages. **Name and version don't enter the hash.** Reordering dependencies
  or channels **does** change it and triggers a rebuild.
- An **unpinned** package keeps the version available at creation, for every
  later environment with the same definition. Pin a version to force a rebuild.
- An unpinned base image tag (`:latest`) can trigger a rebuild each time the tag
  moves.
- The build uses an Entra token to reach the registry, lifetime **60–90
  minutes**, not configurable. A longer build fails.
- Microsoft patches base images every two weeks. Using a patched image means
  **redeploying** whatever uses the old one.

### Lifecycle

- Only **description and tags** can be updated. Anything else is a **new
  version**.
- **Archive** hides an environment from `az ml environment list`. It stays
  usable. A new version under an archived name is archived too.
- **Archiving doesn't delete the cached image.** Use `az acr repository delete`.
- `azureml:<name>@latest` follows the latest version. An **inline** environment
  in a job has no name or version and isn't tracked.

---

## 2. Components

A component is one pipeline step: **metadata** (name, version, type),
**interface** (typed inputs and outputs), **command, code and environment**.

| YAML key | Rule |
| --- | --- |
| `name` | required, unique in the workspace, **starts with a lowercase letter**; lowercase, digits and `_` only |
| `display_name` | free text, not unique |
| `environment` | required |
| `is_deterministic` | default **`true`**: reuse the previous result when inputs are unchanged. Set `false` to force a rerun, for example to reload data from a URL |

- **Literal inputs** (string, number, integer, boolean) are parameters. `min`
  and `max` on numbers are checked **at validation, before submission**.
- **Object inputs** (`uri_file`, `uri_folder`, `mltable`, `mlflow_model`)
  connect steps.
- Adding an input means editing three places: `inputs`, `command`, and the
  source code that parses it.
- Registered components are **versioned**. `az ml component update` changes only
  a few fields (description, display name). `archive` and `restore` exist.

---

## 3. Registries

A registry decouples assets from workspaces: **models, environments,
components, data**. Learn's pattern: train in dev, publish the candidate to the
registry, deploy from the registry to test and prod workspaces, possibly in
other subscriptions.

- The same commands work for both: `az ml <asset> create --registry-name <r>`
  in place of `--workspace-name <w>`.
- **Only named assets.** To reference a component or environment inside a
  registry component, create it in the registry first.
- **Promote a model** from a workspace: `az ml model share` with
  `--share-with-name` and `--share-with-version`, both required. The registry
  copy keeps the link to the job that trained it.
- A pipeline using a registry component runs on the **compute and data of the
  workspace that submits it**.
- **Region:** the workspace's region must be in the registry's supported
  regions, for jobs and for deployments.
- Roles: **AzureML Registry User** to work with assets; Contributor or Owner to
  create or delete registries.
- MLflow's model registry API doesn't support organizational registries; use
  the Azure ML CLI or SDK (`mlflow-tracking-and-model-registry.md`).

---

## 4. What this repository measured, and what it did not

**Measured** (`mlops/training-pipeline/`, `specs/005-…/results.md`,
`compute-cost-model.md` § 7.5):

- **Curated environment pinned by version.** `sklearn-1.5` version 52, read
  from the registry and pinned to avoid `latest`.
- **Batch deployments refused the curated environment.** The repository
  recorded it as "batch deployments reject a registry environment id". Learn's
  batch page states the rule as "Curated environments aren't supported in batch
  deployments" (`batch-endpoints.md` § 2).
- **The MLflow no-code path failed at image build.** Azure ML adds
  `azureml-dataset-runtime` to the synthesised environment, which caps pyarrow
  below 4.0; MLflow 3 needs 4.0 or later. No version satisfies both.
- **A custom environment build created the container registry** and billed
  1.15 h of `E4ds v4` on a day with no node allocation. Consistent with § 1:
  builds run on serverless compute when no build compute is set.

**Not measured:** components, pipelines, registries, environment archive,
hash reuse across renamed environments.

---

## 5. What this note would cost to verify

A registry brings its own storage and container registry, so it has a cost at
rest. The pages read here don't price it. Registering a component and running a one-step pipeline on the existing
cluster costs one activation, about 0.05 €. A custom environment adds a build,
about 0.28 € an hour of build time.

---

## Sources

- [What are Azure Machine Learning environments?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-environments): read 2026-10-01 (ms.date 2025-10-30); § 1 build and cache
- [Manage Azure Machine Learning environments with the CLI and SDK (v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-environments-v2): read 2026-10-01 (ms.date 2026-03-18); § 1 creation and lifecycle
- [What is an Azure Machine Learning component?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-component): read 2026-10-01 (ms.date 2025-10-30); § 2
- [Create and run component-based ML pipelines with the CLI](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-component-pipelines-cli): read 2026-10-01 (ms.date 2026-08-31); § 2 keys
- [Machine learning registries for MLOps](https://learn.microsoft.com/en-us/azure/machine-learning/concept-machine-learning-registries-mlops): read 2026-10-01 (ms.date 2026-07-06); § 3
- [Share models, components, and environments across workspaces with registries](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-share-models-pipelines-across-workspaces-with-registries): read 2026-10-01 (ms.date 2026-02-11); § 3
- [Manage access to Azure Machine Learning workspaces](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles): read 2026-10-01 (ms.date 2026-01-08); registry roles
- `mlops/training-pipeline/`, `specs/005-training-job-batch-endpoint/results.md`, `compute-cost-model.md` § 7.5: § 4
