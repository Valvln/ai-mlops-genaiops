# Compute targets: clusters, instances, serverless

**Status: one compute cluster built and measured; no compute instance.**
`infra/main.bicep` declares `ai300-cpu-cluster`: `Standard_DS1_v2`, dedicated,
min 0, max 2, 120 s idle before scale-down, system-assigned identity, SSH off.
A compute instance was never created, by decision: it bills while running and
its disk bills while stopped. Figures are in `compute-cost-model.md`; this note
holds the documented behaviour.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objective: *Create and manage compute targets*.

---

## 1. Which compute for what

| Target | Managed by Azure ML | Shared | Scales | Typical use |
| --- | --- | --- | --- | --- |
| Compute **cluster** (AmlCompute) | yes | yes, all workspace users | 0 to `max_nodes` per job load | training, batch inference, pipelines, sweeps |
| **Serverless** compute | yes, nothing to create | n/a | per job | training without managing a cluster |
| Compute **instance** | yes | **no**, single user | single node | development, notebooks, test training |
| Kubernetes (attached) | no | yes | yes | training and inference on your cluster |
| Remote VM, Databricks, Synapse Spark, HDInsight | no | | | attached, unmanaged |

Learn now suggests **serverless compute** in place of creating a cluster, "to
offload compute lifecycle management". In a command job, omit `compute`. In a
pipeline, set `default_compute: azureml:serverless`.

AutoML (SDK v2/CLI v2) runs on a compute cluster or a compute instance.

---

## 2. Compute cluster

- **`min_instances: 0`** (`minNodeCount`) lets the cluster deallocate all
  nodes. "Any value larger than 0 will keep that number of nodes running, even
  if they are not in use."
- **Idle time before scale-down** defaults to **120 seconds**. Shorter saves
  cost for occasional jobs; longer suits rapid dev/test iteration.
- Nodes are released as jobs finish, down to the minimum. The cluster never
  exceeds `max_instances`.
- **VM type (CPU or GPU) and SSH access can't be changed after creation.**
- A cluster can be created **in another region** than the workspace (clusters
  only, not instances), with latency and data-transfer cost.
- **Resource locks:** a delete or read-only lock on the workspace's resource
  group **prevents cluster scaling**. Symptom: stuck at *resizing (0 → 0)*.
  Learn's fix: remove the lock from the group and lock individual resources.
- **Low priority:** retired on **2026-03-31**. `tier: low_priority` still
  validates and runs, but nodes are allocated as **Spot VMs** at the variable
  Spot rate, and can be preempted. Low priority has its own quota, separate
  from dedicated. Compute instances can't use it.

### Quota

The dedicated cores per region per VM family quota is **shared** between
clusters and instances.

> "While your compute cluster scales down to zero nodes when not in use,
> unprovisioned nodes contribute to your quota usage. Deleting the compute
> cluster removes the compute target from your workspace, and releases the
> quota."

Setting subscription or workspace-level quota needs **subscription-scope**
permissions.

---

## 3. Compute instance

- **Can't be shared.** Other users who run your notebook use their own
  instance. An administrator can **create on behalf of** a user; the creator
  can't enable SSO on it, the assigned user does.
- **Stopping releases no quota**, so that the instance can restart. Restart
  still depends on regional capacity.
- **VM size can't be changed** after creation.
- **Idle shutdown:** inactive means no Jupyter kernels or terminals, no runs, no
  VS Code connection, no custom applications. Bounds: **15 minutes to 3 days**.
  Via CLI or SDK, idle shutdown is set **only at creation**. Existing instances
  are changed in studio or with the REST API.
- **With a managed identity, idle shutdown doesn't happen** unless the identity
  has Contributor on the workspace.
- **Schedules:** up to four start/stop schedules per instance. Azure Policy can
  enforce a default shutdown schedule.
- The storage account must allow **storage account key access** for instance
  creation to succeed.
- Stopped instances still bill the **P10 OS disk** and the load balancer.

---

## 4. Billing basis

> "Each VM is billed per hour that it runs."

Learn's cost levers for compute: min nodes 0, shorter idle time, quotas per
subscription and workspace, **job termination policies** (sweep early
termination, AutoML exit criteria, job `timeout`), Spot/low-priority, reserved
instances, scheduled instance shutdown, one region for everything.

Learn's pages disagree about an idle cluster at zero nodes:

| Page | Statement |
| --- | --- |
| *Compute targets*, *Manage and optimize cost* | set minimum nodes to 0 "to avoid charges when no jobs are running" |
| *Plan to manage costs* | every 50 cluster nodes bill one standard load balancer, about $0.33 a day; delete the compute to avoid it |
| *Train models* | "The cluster continues to bill while it exists, even with zero nodes running." |

---

## 5. What this repository measured, and what it did not

**Measured** (`compute-cost-model.md` §§ 2, 7.1–7.3, tracker):

- **An idle cluster cost nothing measurable.** No load balancer or
  `*-azurebatch-*` resource appeared in the resource group at zero nodes or with
  one node running, and Cost Management showed no cluster charge on idle days.
  The *Train models* and *Plan to manage costs* statements in § 4 are not what
  this subscription showed. The likely reason, a hypothesis: the networking
  resources belong to VNet-injected clusters.
- **An idle cluster held zero vCPU quota.** `Total Cluster Dedicated Regional
  vCPUs` read 0 at rest and 1 with a node allocated; only the cluster count
  bucket held an entry. This **contradicts the quota quotation in § 2** as far
  as vCPU buckets go. For an exam answer, the documented statement is the one
  that is asked: delete the cluster to release its quota.
- **Billing starts at node allocation.** One activation from cold costs about
  0.05 € on `Standard_DS1_v2`, P10 disk overhead included.
- **Image builds bill on a machine nobody chose** (§ 7.5): 1.15 h of
  `E4ds v4` on the one day with a custom environment. Learn's environment page
  says images build "on available workspace serverless compute quota if no
  dedicated compute set". That matches the observation.

**Not measured:** a compute instance, idle shutdown, serverless compute,
Spot nodes, resource-lock scaling failure, cross-region clusters.

---

## 6. What this note would cost to verify

A compute instance at the smallest size for one hour, with idle shutdown at 15
minutes, costs cents plus the disk while it exists. Delete it in the same
session. Serverless compute for one short job costs the same order as one
cluster activation.

---

## Sources

- [What are compute targets in Azure Machine Learning?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-compute-target): read 2026-10-01 (ms.date 2026-03-31); §§ 1, 4
- [Create an Azure Machine Learning compute cluster](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster): read 2026-10-01 (ms.date 2025-09-11); § 2
- [Create an Azure Machine Learning compute instance](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-compute-instance): read 2026-10-01 (ms.date 2025-08-13); § 3
- [Manage and optimize Azure Machine Learning costs](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-optimize-cost): read 2026-10-01 (ms.date 2026-07-29); §§ 2, 4
- [Plan to manage costs for Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-plan-manage-cost): read 2026-10-01 (ms.date 2026-03-11); § 4
- [Train models with Azure Machine Learning CLI, SDK, and REST API](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-model): read 2026-10-01 (ms.date 2026-05-20); § 4
- [Set up AutoML training for tabular data](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-configure-auto-train): read 2026-10-01 (ms.date 2026-08-21); AutoML compute
- [What are Azure Machine Learning environments?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-environments): read 2026-10-01 (ms.date 2025-10-30); image build compute
- `compute-cost-model.md` §§ 2, 7.1–7.5: § 5
