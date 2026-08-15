# Research: datastore and compute cluster

**Feature**: 004 · **Date**: 2026-08-15 · **Cost of this phase**: 0.00 €

Everything below was read from the live subscription, from the ARM provider
manifest, from the Bicep compiler, or from current Microsoft documentation with
the sentence quoted. Nothing here is recalled. Where a question could not be
settled without deploying, it says so and names the observation that settles it.

---

## R1 — API versions, from the live provider

Read on 2026-08-15 with `az provider show`, not from an example.

```bash
az provider show -n Microsoft.MachineLearningServices \
  --query "resourceTypes[?resourceType=='workspaces/computes'].apiVersions[0:6]" -o tsv
az provider show -n Microsoft.Storage \
  --query "resourceTypes[?resourceType=='storageAccounts/blobServices'].apiVersions[]" -o tsv
```

| Type | Latest available | **Pinned** | Why |
| --- | --- | --- | --- |
| `workspaces/datastores` | `2026-05-15-preview` | **`2026-05-01`** | Latest GA. Identical to the version `main.bicep` already pins for `workspaces` itself, so the whole ML family moves as one. Preview rejected: this template is deployed unattended by CI. |
| `workspaces/computes` | `2026-05-15-preview` | **`2026-05-01`** | As above. |
| `storageAccounts/blobServices/containers` | `2026-04-01` | **`2023-01-01`** | Matches the version `main.bicep` already pins for `storageAccounts`. A container declared at a different version than its own parent account is one more version to reason about for no gain; the container schema has not changed across this range. |

**A wrinkle worth recording.** The provider manifest does **not** enumerate
`storageAccounts/blobServices/containers` as a resource type — only
`storageAccounts/blobServices`. Querying for it returns an empty list, which is
not evidence that the type does not exist; nested child types are frequently
absent from the manifest. The type and its API versions were confirmed a
different way, by compiling them (R2). This is the same class of trap as an
empty `az consumption budget list`: absence of output is not absence of the
fact.

## R2 — The design compiles

A throwaway template declaring all five objects, at the versions pinned above,
built clean:

```text
az bicep build --file probe.bicep --stdout   →   exit 0, no warnings
```

That covers the resource types, the API versions, the property shapes
(`scaleSettings`, `credentialsType`, the nested `properties.properties` of
`AmlCompute`), the compute's `identity` block, and a role assignment scoped to a
blob container. The probe was never deployed and is not committed.

**What this does not prove.** Compiling is not deploying. Region eligibility,
name-length limits and quota are all invisible to the compiler — this repository
has already been bitten once by a storage account name that compiled and would
not deploy. `what-if` against the live subscription is the next gate, and the
deployment itself is the one after that.

## R3 — The node size

The rule comes from the spec (FR-009 to FR-011); the numbers come from
`docs/exam-notes/compute-cost-model.md`, measured 2026-08-11 and not re-measured
here.

**Chosen: `Standard_DS1_v2` — 1 vCPU, 3.5 GB, 0.05774 €/node-hour.**

The arithmetic the spec asks for, against a maximum of 2 nodes:

| Bound | Demand | Limit | Fits |
| --- | --- | --- | --- |
| Per-family dedicated (Standard DSv2) | 2 nodes × 1 vCPU = **2 vCPU** | 6 | yes, 3× headroom |
| Regional dedicated total | **2 vCPU** | 20 | yes |
| Regional low priority | not used | 0 | n/a — see below |

Why not the alternatives:

- **`Standard_A1_v2`** is cheaper (0.03598 €/h) and is offered by
  `az ml compute list-sizes`. Its family quota is **0**. It is the trap the cost
  model documents: *supported by the service* and *allocatable on this
  subscription* are different questions answered by different commands.
- **`Standard_D1_v2`** costs exactly the same and shares the same meter, but is
  not supported for compute instances or managed online endpoints. At an
  identical price, the size that serves all three forms is the better default —
  it costs nothing now and avoids re-choosing later.
- **Low priority at any size** is unavailable. Every low-priority family reports
  a limit of `-1`, which reads as "no limit"; the regional low-priority total is
  `0`, and the regional total gates all of them. The per-family row is the wrong
  row to read.

**Quota is consumed by the cluster, not by its nodes.** From the compute cluster
documentation: *"While your compute cluster scales down to zero nodes when not
in use, unprovisioned nodes contribute to your quota usage. Deleting the compute
cluster removes the compute target from your workspace, and releases the
quota."* So 2 vCPU of the 6 available in the DSv2 family are held for as long as
the cluster exists, at zero nodes and zero cost. Quota and cost are different
ledgers; this is the sentence that separates them.

## R4 — Which identity actually reads the data

This is the question the plan was asked to settle rather than assume, and the
answer changed the design.

### What the documentation says

> "The Azure Machine Learning compute cluster uses a **managed identity** to
> retrieve connection information for datastores from Azure Key Vault and to
> pull Docker images from ACR. You can also configure identity-based access to
> datastores, which uses the managed identity of the compute cluster."

> "To enable authentication by using compute managed identity:
> • Create compute with managed identity enabled.
> • Grant compute managed identity at least **Storage Blob Data Reader** role on
>   the storage account.
> • Create any datastores with identity-based authentication enabled."

> "When you use identity-based data access, Azure Machine Learning prompts you
> for your **Microsoft Entra token** for data access authentication instead of
> keeping your credentials in the datastore."

— [Set up service authentication](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-identity-based-service-authentication)

Its own summary table names the default and the alternative:

| Scenario | Default | Alternative |
| --- | --- | --- |
| Compute cluster in training jobs | **Compute managed identity** | User identity, via job configuration |
| Interactive data access (notebooks, studio) | **User identity** | Workspace managed identity |

So there are three candidate readers, not one: the submitting user's Entra
token, the **compute cluster's** managed identity, and the workspace's managed
identity. Compute managed identity is an **opt-in**: the recipe's first step is
"create compute with managed identity enabled", which means a cluster declared
without an identity does not have one.

### What this subscription says

Data-plane assignments on the storage account, read 2026-08-15:

| Principal | Role | Scope |
| --- | --- | --- |
| The author (`ValerioQuaranta@…`) | **Owner** | storage account |
| Workspace MSI (`9357d31d-…`) | Storage Blob Data Contributor | storage account |
| Workspace MSI | Storage File Data Privileged Contributor | storage account |
| Workspace MSI | Azure AI Administrator | storage account |
| CI deployer (`39fecb6c-…`) | AI300 CI Deployer | resource group |

Two consequences, and both are load-bearing for the plan.

**The author cannot read blob data.** Owner is a management-plane role. It
confers control over the storage account and over who may access it, and
**no data-plane access to blobs** — the identical distinction to the Key Vault
one that cost a mark in the Domain 1 simulation, on a different service. The
author holds no `Storage Blob Data Reader` or `Contributor`.

That is not an obstacle; it is the discriminator this feature needs. If the read
were happening as the author's identity, **it would fail**. So a job that
successfully reads the file has demonstrably read it as something other than the
author — which is precisely the claim FR-018 makes, and it is provable rather
than asserted.

**The workspace MSI can read the new container.** Its
`Storage Blob Data Contributor` grant sits at **storage account scope**, so it
covers any container created under that account, including one the platform did
not create. The ABAC condition that would narrow it to workspace-owned
containers applies only when `enableDataIsolation` is set, and the default for a
workspace of kind `default` is disabled.

### The decision, and the trap inside it

**Decision: the cluster is declared with a system-assigned managed identity, and
the template grants that identity `Storage Blob Data Reader` scoped to the
training container.**

Reasons, in order of weight:

1. It is the documented recipe for this scenario, all three steps of which this
   design performs.
2. It removes the ambiguity. Without a compute identity, the reader is whichever
   of the remaining two candidates the service picks, and the job result would
   not tell us which.
3. **The grant is one this repository owns.** Feature 002's whole finding was
   that the workspace identity's permissions are the platform's to maintain, so
   least privilege was unreachable there. The compute cluster's identity is not
   auto-granted anything on storage — the documentation says an admin must grant
   it — so this is a grant that can be scoped, withdrawn, and tested.
4. Scoping it to the **container** rather than the storage account is the
   narrowest scope that works, and costs nothing to do.

**And here is the trap.** Because the workspace MSI already holds
`Storage Blob Data Contributor` at account scope, a job could succeed by that
path while the container grant does nothing whatsoever. The check "the job read
the file" would be green, and the grant this feature added would be **inert** —
which is exactly the outcome feature 002 produced with its Key Vault assignment,
and exactly the shape of failure this repository has now hit twice.

So the design carries a **necessity test**, borrowed from feature 003's FR-008:
after the job succeeds, remove the container grant and run the job again.

| Second run | What it means |
| --- | --- |
| **Fails** with an authorisation error | The grant is load-bearing. The compute identity is the reader. Restore the grant and the feature is honest. |
| **Succeeds** | The grant is decoration. Something else authorised the read — almost certainly the workspace MSI at account scope. The grant is then either removed from the template or kept with a comment saying plainly that it is inert, in the manner of `main.bicep`'s existing Key Vault assignment. |

Both outcomes are acceptable and both are findings. What is not acceptable is
shipping the grant without knowing which one is true. Cost of the test: one
extra short job, single-digit node-minutes.

## R5 — Idle time before scale-down

**Chosen: 120 seconds — the service default, declared explicitly.**

The reasoning matters more than the number. The documentation:

> "You can also configure the amount of time the node is idle before scale down.
> By default, idle time before scale down is set to 120 seconds."

FR-007 requires the value to be **chosen**, not inherited. Two minutes at
`DS1_v2` is 0.002 € of billed tail per job — financially irrelevant, and that is
the point: there is no cost argument for shortening it, and there is a real
argument against. A shorter interval makes the cluster tear down and re-allocate
nodes between closely spaced jobs, and node allocation costs minutes of wall
clock. The default is the right value here; what was wrong was not having read
it.

Declaring it also makes the mechanism visible in the template, which is the part
the exam asks about. A value that matches the default but is written down is a
decision; the same value left blank is an assumption.

## R6 — Predicted authorisation failures

**These are predictions. Nothing is added to the CI role until a run names it**
(FR-013). The list exists so the failures are recognised in seconds instead of
diagnosed from scratch — and so that a failure that is *not* on the list is
noticed as interesting.

The role currently permits thirteen operations, none of them on the three new
types. Predicted, in the order ARM is likely to demand them:

| # | Predicted operation | Confidence | Why |
| --- | --- | --- | --- |
| 1 | `Microsoft.Storage/storageAccounts/blobServices/containers/write` | high | New declared type |
| 2 | `Microsoft.MachineLearningServices/workspaces/datastores/write` | high | New declared type |
| 3 | `Microsoft.MachineLearningServices/workspaces/computes/write` | high | New declared type |
| 4 | `…/containers/read` | medium | Feature 003 established that reads surface separately from writes, one run later |
| 5 | `…/datastores/read` | medium | As above |
| 6 | `…/computes/read` | medium | As above |
| 7 | `Microsoft.Storage/storageAccounts/blobServices/read` | low | The container's parent is referenced as `existing` |

Already held, so predicted **not** to fail:
`Microsoft.Authorization/roleAssignments/write`, which the new container grant
needs and which feature 003 added for the Key Vault assignment. If the container
grant fails on authorisation anyway, that is a finding about assignment scope
rather than about the role's action list.

**Cost of this discovery, in the currency that is actually scarce here.** Each
failure is one gated deployment, and each gate is an approval by the author.
Between four and seven approvals is the realistic range. The money is zero;
the author's attention is not. This is the price of a role narrow enough to be
worth having, and feature 003 accepted it deliberately.

**One mitigation that does not cheat.** Deploying `main.bicep` by hand first, as
the author, separates template defects from authorisation defects. It does not
pre-authorise anything and does not reduce the number of operations discovered —
ARM issues the same writes on an idempotent redeployment, so CI still fails on
exactly the operations it lacks. What it removes is the case where a red run is
a template bug wearing an authorisation error's clothes. See R8 for where this
sits in the order.

## R7 — Why creating a cluster is the moment the resource-group question answers itself

The tracker has carried this open question since feature 002: *is the grant on
the resource group actually needed?* `main.bicep` sets
`allowRoleAssignmentOnRG: false`, which removed the workspace identity's
resource-group-wide `Azure AI Administrator` grant — whereupon the platform
created three resource-scoped grants of equivalent authority instead.

The mechanism that makes a compute cluster the test is documented, and it is
more specific than "compute needs permissions". Creating an AmlCompute cluster
causes the platform to create **networking resources in the workspace's resource
group**, named for the Batch service that manages the cluster:

> "**Do not** apply the lock to the following resources:
> `<GUID>-azurebatch-cloudservicenetworksecuritygroup` (network security group),
> `<GUID>-azurebatch-cloudservicepublicip` (public IP address),
> `<GUID>-azurebatch-cloudserviceloadbalancer` (load balancer). These resources
> are used to communicate with, and perform operations such as scaling on, the
> compute cluster."
> — [Create compute clusters](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster)

Writing three resources into the resource group is exactly the authority that
was withdrawn at resource-group scope. So the question becomes answerable by
looking, and the observation is cheap: after the cluster is created, list the
resource group and see whether those three objects are there.

| Observation | Reading |
| --- | --- |
| The three `*-azurebatch-*` resources exist, cluster works | The withdrawn resource-group grant was **not** needed for this. The platform's three resource-scoped grants, or its own service principal, sufficed. |
| Cluster creation fails with an authorisation error | The grant **was** load-bearing. Record the error verbatim; the documented remedy is to set the property back to `true` and redeploy, which `infra/DEPLOY.md` already anticipates. |

Either way it is written down with its date. Neither is a defect.

## R8 — The same three resources are the load-balancer answer

The cost model listed as unverified: *does a cluster resting at zero nodes
still bill a load balancer?* The documentation states the rule without stating
the boundary:

> "For each compute instance, one load balancer is billed per day. Every 50
> nodes of a compute cluster have one standard load balancer billed. Each load
> balancer is billed around $0.33/day. **To avoid load balancer costs on stopped
> compute instances and compute clusters, delete the compute resource.**"
> — [Plan to manage costs](https://learn.microsoft.com/en-us/azure/machine-learning/concept-plan-manage-cost)

The two halves point opposite ways. "Every 50 nodes … have one" reads as zero
load balancers at zero nodes. "To avoid load balancer costs on **stopped**
compute clusters, delete the compute resource" reads as a charge that survives
scaling to zero — otherwise the sentence would have nothing to say about
clusters.

R7 supplies the physical evidence that settles which is right, because
`<GUID>-azurebatch-cloudserviceloadbalancer` is a real resource that either
exists in the resource group or does not. Existence is not billing, so the
observation has two steps and both are needed:

1. **Does the object exist while the cluster rests at zero nodes?** Read the
   resource group. Available minutes after the cluster is created.
2. **Does it produce a charge?** Read Cost Management for a period covering at
   least one full day at rest, looking for a load balancer meter. Available a
   day or two later, which is after this session closes.

If the answer is that it bills, roughly 0.30 €/day, then a cluster is not a
free-at-rest object after all and the shutdown procedure for the rest of this
project changes from "leave it, it costs nothing" to "delete it at the end of
the week". That is a consequential finding and it is worth the wait.

---

## Consolidated decisions

| # | Decision | Rationale | Rejected alternative |
| --- | --- | --- | --- |
| D1 | Datastore and cluster declared in `infra/main.bicep` | One template, deployed one way, through the gate | A separate template — splits the deployment path for no gain |
| D2 | ML types at `2026-05-01`, container at `2023-01-01` | Latest GA, matching each resource's own parent | Preview versions — unattended CI deployment |
| D3 | `Standard_DS1_v2`, dedicated, min 0 / max 2 | Cheapest allocatable; 2 vCPU against a family limit of 6 | `A1_v2` (family quota 0), low priority (regional quota 0) |
| D4 | Idle scale-down 120 s, declared | The default is correct; not reading it was not | A shorter interval — re-allocation costs more than the tail |
| D5 | A dedicated blob container, not the workspace's own | Training data and system artifacts do not share a location | Reusing `workspaceblobstore` — cheaper today, awkward later |
| D6 | Cluster gets a system-assigned identity; template grants it `Storage Blob Data Reader` at **container** scope | The documented recipe; the only grant here this repository owns and can scope | No compute identity — reader becomes ambiguous, and the author's identity would fail |
| D7 | The grant's necessity is tested by removing it and re-running | The workspace MSI's account-scope grant could be doing the work; that is how 002 shipped an inert assignment | Trusting a green job — the failure mode this repository has hit twice |
| D8 | Predicted CI failures recorded, none pre-authorised | FR-013; the record makes failures readable without granting anything | Adding the seven predicted operations up front |

## Still open at the end of Phase 0

These are not gaps in the plan; they are what the plan exists to observe.

| Question | Settled by | When |
| --- | --- | --- |
| Which operations the CI role actually lacks | The failing runs themselves | During deployment |
| Whether the withdrawn resource-group grant is needed | Cluster creation succeeding or failing (R7) | At first cluster deployment |
| Whether the container grant is load-bearing or inert | The necessity test (R4, D7) | After the first successful job |
| Whether a cluster at zero nodes bills a load balancer | Resource existence, then a cost reading over a full day (R8) | Existence: same session. Charge: 24–48 h later |
