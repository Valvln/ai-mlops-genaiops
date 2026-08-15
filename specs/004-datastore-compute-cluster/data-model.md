# Data model: the objects this feature declares

**Feature**: 004 · **Date**: 2026-08-15

Four declared objects and one job asset. Every property that is written down is
written down because a decision was made about it; nothing here is a default
that happened to be typed out. Where a value equals the service default, the
table says so and says why it is still declared.

---

## 1. Training data container

**Type**: `Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01`
**Parent**: the `default` blob service of the existing storage account
**Cost**: per GB stored. A sample file of a few kilobytes is not measurable.

| Property | Value | Why |
| --- | --- | --- |
| `name` | `training-data` | Fixed, not derived from `uniqueString()`. Container names are scoped to the account, so no global collision is possible, and a stable name is one the job asset can reference without a parameter. |
| `publicAccess` | `None` | Anonymous read would defeat the entire identity-based design. Declared rather than defaulted because "the default is private" is the kind of thing that is true until it is not. |

**Why a new container at all.** The workspace creates its own containers for
system artifacts. Putting training data there would work today and would mean
that clearing workspace state and clearing training data are the same operation.
The cost of separating them now is one resource.

---

## 2. Training data datastore

**Type**: `Microsoft.MachineLearningServices/workspaces/datastores@2026-05-01`
**Parent**: the existing workspace
**Cost**: none. A datastore is metadata; it holds no data.

| Property | Value | Why |
| --- | --- | --- |
| `datastoreType` | `AzureBlob` | Blob is one of the three types that support identity-based access at all (R4). |
| `accountName` | the existing storage account | FR-002: no new storage account. |
| `containerName` | `training-data` | Object 1. |
| `protocol` | `https` | Explicit. |
| `endpoint` | `environment().suffixes.storage` | Resolved from the deployment's cloud rather than written as a literal. |
| `credentials.credentialsType` | **`None`** | **The load-bearing property of this feature.** It is what makes the datastore credential-less: no account key, no SAS, nothing cached in the key vault. FR-003. |
| `description` | states that access is by identity | The property name `None` reads like "unset" rather than like a decision. It is a decision. |

**What `credentialsType: 'None'` buys.** With a key or SAS, the credential is
cached in the workspace's key vault, and anyone with sufficient permissions on
that vault can retrieve it. With `None` there is nothing to retrieve, and access
is decided at the storage account by RBAC — which is what makes objects 3 and 4
meaningful.

---

## 3. Compute cluster

**Type**: `Microsoft.MachineLearningServices/workspaces/computes@2026-05-01`
**Parent**: the existing workspace
**Cost**: **0.00 € at rest.** 0.05774 € per node-hour while a job runs.

| Property | Value | Why |
| --- | --- | --- |
| `identity.type` | `SystemAssigned` | Makes the cluster a principal that can be granted data access and, unlike the workspace's identity, one whose grants this repository owns (R4, D6). Without it the reader of the datastore is ambiguous. |
| `location` | `northeurope` | Same region as the workspace. A cluster *can* live elsewhere; the documentation warns it adds latency and data transfer charges. |
| `computeType` | `AmlCompute` | The managed cluster form. |
| `properties.vmSize` | **`Standard_DS1_v2`** | Cheapest allocatable: family quota 6 against a demand of 2 vCPU, where the cheaper `A1_v2` has a family quota of 0 (R3). |
| `properties.vmPriority` | **`Dedicated`** | Low priority is unavailable: regional quota 0, and the per-family `-1` readings are gated by it (R3, FR-010). |
| `properties.osType` | `Linux` | The Linux meter is the one the price table uses; the Windows meter is roughly double. |
| `properties.remoteLoginPortPublicAccess` | `Disabled` | SSH is not needed and cannot be changed after creation. |
| `scaleSettings.minNodeCount` | **`0`** | FR-005. The single property that makes the cluster free at rest. Note it is the *request*; SC-002 checks the *result*. |
| `scaleSettings.maxNodeCount` | **`2`** | FR-006. Bounds a runaway job at ~2.77 €/day and leaves batch scoring across nodes demonstrable. 2 vCPU against a family limit of 6. |
| `scaleSettings.nodeIdleTimeBeforeScaleDown` | **`PT120S`** | FR-007. Equal to the service default, and declared anyway: the requirement is that the value be chosen. R5 explains why 120 s is the right choice rather than a shorter one. |

**Naming**: fixed and human-readable rather than derived from
`uniqueString(resourceGroup().id)`. Compute names are scoped to the workspace,
so the collision that forced derived names for the storage account and key vault
does not arise, and every `az ml` command in the runbook and in `quickstart.md`
can name it literally. The name must be 3–24 characters, start with a letter,
and be unique within the region for the workspace.

**Quota is held, cost is not.** ~~The cluster reserves 2 vCPU of DSv2 family
quota for as long as it exists, at zero nodes and zero cost.~~

**Measured 2026-08-15, and it does not:** with the cluster deployed and idle,
the DSv2 family bucket and the regional dedicated bucket both read `used = 0`.
The only bucket that moves is `Total Clusters`, from 0 to 1. See the correction
box in [research.md § R3](./research.md) — the original sentence was inferred
from documentation rather than read from the subscription, which is the mistake
this project keeps rediscovering. Whether vCPU quota tracks allocated nodes is
confirmed when the verification job holds one.

---

## 4. Container read grant

**Type**: `Microsoft.Authorization/roleAssignments@2022-04-01`
**Scope**: the training data container — **not** the storage account
**Cost**: none.

| Property | Value | Why |
| --- | --- | --- |
| `roleDefinitionId` | `Storage Blob Data Reader`, `2a2b9908-6ea1-4ae2-8e65-a410df84e7d1` | Verified against the live tenant on 2026-08-15, in the manner feature 002 established. Read, not Contributor: the job reads. Reached through `subscriptionResourceId()` so no subscription id is written down. |
| `principalId` | the cluster's system-assigned identity | Object 3. The symbolic reference creates the dependency; no `dependsOn` is needed. |
| `principalType` | `ServicePrincipal` | Skips a directory lookup on a principal that may be seconds old. This is feature 002's `PrincipalNotFound` lesson, and it is the reason a *newly created* identity does not fail intermittently here. |
| `name` | `guid(container.id, cluster.id, roleId)` | Deterministic, so redeployment is idempotent. |
| `scope` | the container | The narrowest scope that works. The account-scope alternative would grant read over the workspace's own system containers too, for no benefit. |

### This object may be inert, and that is checked rather than hoped

The workspace's managed identity already holds `Storage Blob Data Contributor`
at **storage account** scope, which covers this container. If the job's read is
performed by the workspace identity rather than by the cluster's, this
assignment authorises nothing.

That is precisely what `main.bicep`'s existing Key Vault Secrets User assignment
turned out to be — kept, but documented as inert. **Shipping a second one
without knowing would repeat feature 002's mistake at a lower level.**

The test is in the plan as step 13: remove the grant, re-run the job.

| Result | Conclusion | Action |
| --- | --- | --- |
| Job fails on authorisation | Load-bearing | Restore it; say so in the comment |
| Job succeeds | Inert | Say so plainly in the comment, in the manner of the existing Key Vault assignment, or remove it |

---

## 5. The verification job

Not a declared Azure resource — a set of files in `mlops/datastore-check/`,
submitted with `az ml job create`. It exists to settle SC-003 and nothing else.

| File | Contents | Why |
| --- | --- | --- |
| `sample.csv` | A few rows of trivial CSV, with its byte count and sha256 recorded in the repository | The **known** file. "Known" is what makes the job's output checkable. |
| `check_datastore.py` | Reads the input path, prints byte count, sha256, and row count | Output derived from the bytes. A job that started but read nothing cannot produce these. |
| `job.yml` | Command job: the script, a curated environment, the cluster as compute, the file as an input via the datastore URI | Declares which compute and which input; the input is addressed through the datastore, so a broken datastore breaks the job. |

**Why a checksum and not "the job exited zero".** An exit code proves a process
ran. The specification's edge case is explicit: a job that starts, logs and
exits zero would satisfy a naive check while proving nothing about data access.
A sha256 that matches a value recorded before the job existed cannot be produced
without the bytes.

**Job identity**: declared explicitly rather than left to the default, for the
same reason the idle interval is. R4 established that the reader is otherwise
one of three candidates.

**Environment**: a curated Azure ML environment, not a custom Docker image. A
custom image would need a container registry, which the workspace deliberately
does not have — `main.bicep` omits `containerRegistry` precisely so one is not
provisioned.

---

## What is deliberately absent

| Not declared | Why |
| --- | --- |
| A second storage account | FR-002. Another billing surface for nothing. |
| A compute instance | ~25 €/month while stopped. FR-008. |
| An online endpoint or deployment | ~42 €/month idle. FR-008. |
| A batch endpoint | Out of scope. The cluster is shaped so one can run on it later. |
| A container registry | Nothing needs one, and the workspace omits it on purpose. |
| Any change to the workspace's own identity or `allowRoleAssignmentOnRG` | Feature 002's territory. If the cluster's creation proves the resource-group grant is needed, that is a finding to record (R7), and the change is proposed separately rather than smuggled in here. |
