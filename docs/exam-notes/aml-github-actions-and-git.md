# GitHub Actions and Git for Azure Machine Learning

**Status: built and measured for infrastructure deployment.** CI deploys
`infra/main.bicep` over OIDC, behind a GitHub environment that requires a human
approval (`.github/workflows/infra-deploy.yml`). No workflow in this repository
submits a training job or a pipeline. Learn's GitHub Actions article for Azure
ML is about that second case.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Configure GitHub integration with
Machine Learning to enable secure access*, *Automate resource provisioning by
using GitHub Actions workflows*, *Manage source control for machine learning
projects by using Git*.

---

## 1. Authentication from GitHub Actions

Learn ranks the options:

| Option | Secret stored in GitHub | Learn's verdict |
| --- | --- | --- |
| **OIDC** with a federated credential on a **Microsoft Entra application** | none | recommended |
| **OIDC** with a federated credential on a **user-assigned managed identity** | none | recommended |
| Service principal with a client secret (`AZURE_CREDENTIALS` JSON) | the secret | "less secure and not recommended" |

The `--json-auth` (formerly `--sdk-auth`) output used to build
`AZURE_CREDENTIALS` is **deprecated**.

### What an OIDC workflow needs

```yaml
permissions:
  id-token: write          # lets the job request the OIDC token
jobs:
  build:
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

- Three values: client ID, tenant ID, subscription ID. No client secret.
  Learn recommends storing the three as GitHub secrets.
- The federated credential on the Entra application or managed identity
  "trust[s] tokens issued by GitHub Actions to your GitHub repository".
- **Public repositories:** use **environment secrets**. If the environment
  requires approval, the job can't read its secrets until a required reviewer
  approves.
- After `azure/login`, the workflow installs the `ml` CLI extension and runs
  `az ml job create` against a job or pipeline YAML.

### Triggers in Learn's example

`workflow_dispatch`, a `schedule` (cron), and `pull_request` on matching branches
and paths. A pipeline in that workflow is an **Azure ML pipeline** (data to
model). Learn's pipeline comparison places code and app orchestration (CI/CD,
approval queues, gating) in Azure Pipelines or similar, and model orchestration
in Azure ML pipelines.

---

## 2. Git integration with jobs

When you submit a job from the CLI or Python SDK and the source folder is in a
Git repository, Azure ML records Git information on the job:

| Property | Source command |
| --- | --- |
| `azureml.git.repository_uri` / `mlflow.source.git.repoURL` | `git ls-remote --get-url` |
| `azureml.git.branch` / `mlflow.source.git.branch` | `git symbolic-ref --short HEAD` |
| `azureml.git.commit` / `mlflow.source.git.commit` | `git rev-parse HEAD` |
| `azureml.git.dirty` | `git status --porcelain .` |

- The information comes from the **local** repository at submission time, so
  any Git host works.
- **No Git information is recorded** if `git` isn't on the PATH of the
  submitting environment, or the code isn't inside a cloned repository. Learn's
  check: `git --version`.
- `azureml.git.dirty: True` means the submitted code doesn't match the recorded
  commit.
- Read it with `az ml job show --query properties` or from the job's raw JSON
  in studio.

### Git on a compute instance

Clone into your user directory on the workspace file share
(`~/cloudfiles/code/`) so other users don't collide on your branch. The local
disk of the compute instance is faster and is lost when the instance is
deleted. SSH keys generated on the instance are readable only by its owner.

---

## 3. What this repository measured, and what it did not

**Measured** (`specs/003-ci-oidc-deploy/`, `infra/DEPLOY.md` § 5, `README.md`):

- **OIDC with no stored secret.** `infra-deploy.yml` has
  `permissions: id-token: write` and logs in with `azure/login` and the three
  IDs. This matches § 1.
- **Approval through a GitHub environment** (`azure-deploy`). Learn mentions
  environment approval as a way to protect secrets. The repository uses it as a
  human gate in front of every deployment.
- **A custom role with a fixed operation list.** The CI identity was built by
  letting the deployment fail and adding each operation the error named. Learn's
  article grants a broad role to the service principal. Least privilege for the
  CI identity is a repository decision.
- **A failing `az` command may never reach Azure.** Removing the grant produced
  a client-side `No subscriptions found`. Only raw HTTP (403 without the grant,
  201 with it) proved the boundary.

**Not measured:** a workflow that submits an Azure ML job; Git properties on a
job (the jobs in feature 005 were submitted from this repository, and their
`azureml.git.*` properties were never read); a federated credential on a
user-assigned managed identity.

---

## 4. What this note would cost to verify

Reading the Git properties of an existing job costs nothing, but every job of
feature 005 died with the teardown of its workspace. A new job on the existing
`Standard_DS1_v2` cluster costs a few cents (`compute-cost-model.md` § 7.3).

---

## Sources

- [Use GitHub Actions with Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-github-actions-machine-learning): read 2026-10-01 (ms.date 2026-03-19); § 1
- [Set up MLOps with GitHub](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-setup-mlops-github-azure-ml): read 2026-10-01 (ms.date 2026-03-19); OIDC recommendation, `--json-auth` deprecation
- [What are Azure Machine Learning pipelines?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines): read 2026-10-01 (ms.date 2026-09-09); pipeline comparison
- [Git integration for Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-train-model-git-integration): read 2026-10-01 (ms.date 2026-06-04); § 2
- `.github/workflows/infra-deploy.yml`, `specs/003-ci-oidc-deploy/`, `infra/DEPLOY.md` § 5: § 3
