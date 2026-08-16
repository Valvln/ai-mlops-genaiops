# The Azure ML compute cost model — measured, not remembered

Week 2 opens the first hourly cost of this project. This note exists so that
decision is taken against figures that were read from an API or a live
subscription, not from memory or from a pricing page skimmed once.

**Measured on**: 2026-08-11
**Subscription**: `5900fbc9-a139-49ed-9987-ba560c147eb7`
**Region**: `northeurope`
**Workspace used for the quota queries**: `ai300ml2mgou37pfmjou` in
`rg-ai300-test01`
**Currency**: EUR, requested explicitly from the pricing API. Two figures below
are in USD because the only source that states them states them in USD; they
are labelled.

Every number carries its source. Where a number could not be verified, it says
so instead of being rounded to something plausible.

---

## 0. How to reproduce every figure here

Two sources, and nothing else.

**Public retail prices** — no authentication, no cost, safe to run:

```bash
curl -s "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode=EUR&\$filter=armRegionName%20eq%20'northeurope'%20and%20armSkuName%20eq%20'Standard_DS1_v2'" \
  | python3 -m json.tool
```

**This subscription's own state** — all read-only:

```bash
export PATH="/usr/local/bin:$PATH"

# What kind of subscription this is
az rest --method get --url "https://management.azure.com/subscriptions/5900fbc9-a139-49ed-9987-ba560c147eb7?api-version=2022-12-01" \
  --query "subscriptionPolicies"

# What can actually be allocated
az ml compute list-usage -g rg-ai300-test01 -w ai300ml2mgou37pfmjou -o table

# Which sizes Azure ML supports here, and for which compute type
az ml compute list-sizes -g rg-ai300-test01 -w ai300ml2mgou37pfmjou -o json
```

Microsoft documentation is cited inline where it states a billing *rule* rather
than a *price*. A rule that only appears in a forum answer is not cited.

---

## 1. Correction: this is not a free trial subscription

The premise this note started from was that costs land on an Azure free trial.
ARM says otherwise:

```
quotaId              : PayAsYouGo_2014-09-01
spendingLimit        : Off
state                : Enabled
```

Two consequences, and both matter more than any price below:

| What was assumed | What is true |
| --- | --- |
| Free trial credit absorbs the first costs | Offer is **Pay-As-You-Go**. Whether trial credit remains is **not verifiable** from these APIs — check the portal's Cost Management → Credits |
| A spending limit stops spending at zero credit | Spending limit is **Off**. Nothing stops spend automatically |

A budget alert is an *alert*. It emails; it does not cap. With
`spendingLimit: Off` there is no automatic ceiling on this subscription, so
every figure in section 4 is money, not credit.

`az consumption budget list` returns `[]` at subscription scope. That is **not**
proof that no budget exists — the command is in preview and a budget created in
the portal may sit at a scope it does not read. Confirm the budget alert in the
portal before the first hourly resource is created.

---

## 2. Quota — what can actually be allocated

Observed, `az ml compute list-usage`, 2026-08-11. All `used` values were 0.

| Bucket | Limit |
| --- | --- |
| Total Clusters | 200 |
| **Total Cluster Dedicated Regional vCPUs** | **20** |
| **Total Cluster Low Priority Regional vCPUs** | **0** |

Per-family dedicated vCPU limits that are greater than zero:

| Family | Limit | Family | Limit |
| --- | --- | --- | --- |
| Standard ESv3 | 20 | Standard D / Dv2 / Dv3 | 6 each |
| Standard FSv2 | 16 | Standard DSv2 / DSv3 | 6 each |
| Standard DASv4 | 10 | Standard EAv4 / Ev3 | 6 each |
| Standard EDSv4 | 10 | Standard DDSv4 / LSv2 | 6 each |
| | | Standard NC / NV | 6 each |

Everything else is 0, including **Standard Av2**.

### Three traps, all of which this session walked into

**The cheapest size is not allocatable.** `Standard_A1_v2` is the cheapest size
Azure ML supports here (§3) and it is offered by `az ml compute list-sizes`. Its
family quota is **0**. "Supported by Azure ML" and "allocatable on this
subscription" are different questions, answered by different commands.

**Low priority is unavailable, and the per-family numbers hide it.** Every
low-priority family reports a limit of `-1`, which reads as "no limit". The
regional total is `0`, and the regional total gates all of them. So the
low-priority discount (roughly 20% of the dedicated rate for `DS1_v2`) and the
low-priority path in batch endpoints are both **out of reach here**. The
per-family row is not the answer; the regional row is.

**`az vm list-usage -l northeurope` returns zero entries on this subscription.**
That is not a quota of zero. `Microsoft.Compute` is `NotRegistered` — the five
providers registered for `main.bicep` do not include it — so the command has
nothing to enumerate. An empty list is not a zero. Azure ML compute quota is
never in `az vm list-usage`; it is in `az ml compute list-usage`.

### Compute instances draw from the same buckets

> "The dedicated cores per region per VM family quota and total regional quota,
> which applies to compute instance creation, is unified and shared with Azure
> Machine Learning training compute cluster quota. Stopping the compute instance
> doesn't release quota to ensure you can restart the compute instance."
> — [What is an Azure Machine Learning compute instance?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-compute-instance)

A stopped compute instance therefore still consumes 20-vCPU regional headroom.
Only deleting it returns the quota.

---

## 3. The price of a node-hour

Azure Retail Prices API, `northeurope`, EUR, `type: Consumption`, Linux rate,
non-spot, non-low-priority. Azure ML compute instances run Ubuntu, so the Linux
meter is the applicable one — the Windows meter for the same size is roughly
double and does not apply.

| Size | vCPU | RAM GB | €/hour | Family quota | Allocatable |
| --- | --- | --- | --- | --- | --- |
| `Standard_A1_v2` | 1 | 2.0 | 0.03598 | **0** | **no** |
| `Standard_D1_v2` | 1 | 3.5 | 0.05774 | 6 | yes — cluster only |
| **`Standard_DS1_v2`** | **1** | **3.5** | **0.05774** | **6** | **yes — all three forms** |
| `Standard_F2s_v2` | 2 | 4.0 | 0.08425 | 16 | yes |
| `Standard_D2s_v3` | 2 | 8.0 | 0.09390 | 6 | yes |
| `Standard_DS2_v2` | 2 | 7.0 | 0.11584 | 6 | yes |
| `Standard_DS11_v2` | 2 | 14.0 | 0.16235 | 6 | yes |

`Standard_D1_v2` and `Standard_DS1_v2` share one meter (`D1 v2/DS1 v2`) at the
same rate, but only `DS1_v2` is supported for compute instances and for managed
online endpoints. At an identical price, `DS1_v2` is the correct default: it is
the one size that serves all three compute forms.

**The cheapest size actually available for a cluster in `northeurope` on this
subscription is `Standard_DS1_v2` at 0.05774 €/node-hour**, not `A1_v2`.

### There is no Azure ML surcharge on CPU compute

The `Azure Machine Learning` service publishes exactly 11 meters in
`northeurope`, and all of them are vCPU surcharges rather than compute rates:

| Meter | €/hour |
| --- | --- |
| Standard vCPU Surcharge | **0.00** |
| Standard Training vCPU Surcharge | **0.00** |
| vCPU Surcharge (all five Enterprise Inferencing products) | **0.00** |
| Standard Training GPU Surcharge | 0.00 |
| Standard GPU Surcharge | 0.096534 |
| PB vCPU Surcharge | 0.048267 |

So the cost of Azure ML CPU compute *is* the underlying VM price. This agrees
with the product documentation:

> "Managed online endpoints are based on Azure Machine Learning compute. When
> you use a managed online endpoint, you pay for the compute and networking
> charges. There's no added surcharge."
> — [Online endpoints for real-time inference](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-online)

The two non-zero meters are legacy Enterprise-edition surcharges. Whether they
still apply to any v2 workload is **not verified**, and no exercise in this
repository is planned on GPU, so it does not need to be.

---

## 4. The four compute forms

### 4.1 AmlCompute cluster with `min_nodes: 0`

**At rest: no compute charge.** This is a documented guarantee, not an
inference:

> "To avoid charges when no jobs are running, **set the minimum nodes to 0**.
> This setting allows Azure Machine Learning to de-allocate the nodes when they
> aren't in use. Any value larger than 0 will keep that number of nodes running,
> even if they are not in use."
> — [Manage and optimize costs](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-optimize-cost)

**While running: the VM rate per node-hour**, from the table in §3.
`Standard_DS1_v2` → 0.05774 € per node-hour.

**The tail nobody budgets for.** The same page: *"You can also configure the
amount of time the node is idle before scale down. By default, idle time before
scale down is set to 120 seconds."* Every job therefore carries two extra
minutes of billed node time after it finishes, unless the setting is lowered.
At `DS1_v2` that is 0.002 € per job — irrelevant to the budget, but it is the
mechanism, and the mechanism is what the exam asks about.

**One unresolved cost at rest.** The cost-planning page states that *"Every 50
nodes of a compute cluster have one standard load balancer billed"* and that
*"To avoid load balancer costs on stopped compute instances and compute
clusters, delete the compute resource."* Whether a cluster resting at **0
nodes** still bills a load balancer is **not stated and not verified**. See §7 —
this is the first thing to measure when the cluster is created.

### 4.2 Compute instance

**Running**: the VM rate, same table. `Standard_DS1_v2` → 0.05774 €/hour.

**Stopped**: the compute charge stops. Two charges do not.

> "Compute instances also incur P10 disk costs even in stopped state because any
> user content saved there persists across the stopped state similar to Azure
> VMs. The OS disk on a compute instance has a 120-GB capacity."
>
> "For each compute instance, one load balancer is billed per day. [...] Each
> load balancer is billed around $0.33/day. To avoid load balancer costs on
> stopped compute instances and compute clusters, delete the compute resource."
> — [Plan to manage costs](https://learn.microsoft.com/en-us/azure/machine-learning/concept-plan-manage-cost)

| While stopped | Amount | Source |
| --- | --- | --- |
| P10 LRS managed OS disk | **17.2971 €/month** | Retail Prices API, `northeurope` |
| Standard load balancer, 1 per instance | **≈ 0.33 USD/day ≈ 10 USD/month** | Microsoft docs, in USD. The EUR meter was **not found** in the retail API for `northeurope` — treat as an unconverted documented figure |

**So a stopped compute instance costs on the order of 25–27 € per month while
doing nothing.** That is more than the entire deployment currently costs, and it
is the single most expensive way to be careless in Week 2.

The operational conclusion is not the usual one. "Stop the compute instance when
you are not using it" is the advice everywhere, and it is the right advice when
you will be back tomorrow. For this project, where a compute instance is needed
for one exercise and then not again for a week, the correct action is
**delete**, not stop. Deleting also returns the quota (§2).

Idle shutdown and start/stop schedules exist and are worth knowing for the exam,
but they solve the wrong problem here: they stop the hourly charge, which
deleting also does, and they leave the disk and the load balancer running, which
deleting does not.

Low-priority is not an option for this form at all: *"Low-Priority VMs don't
work for compute instances, since they need to support interactive notebook
experiences."*

### 4.3 Managed online endpoint with no traffic

**This is the question that was answered wrong in the Domain 1 simulation, so it
is written out in full.**

The endpoint and the deployment are two different objects, and only one of them
costs anything.

| Object | What it is | Billed |
| --- | --- | --- |
| **Endpoint** | a named HTTPS address plus a traffic-routing rule | **nothing** |
| **Deployment** | the model, the environment, and `instance_count` VMs running it | **the VMs, continuously** |

The documentation attributes the cost explicitly: *"Costs applied to: Virtual
machines (VMs) assigned to the deployment."*

The word that carries the whole answer is **assigned**. `instance_count` is a
reservation, not a reaction to load. The instances are allocated when the
deployment is created and released when it is deleted. Requests do not start
them and idleness does not stop them. Autoscale moves the count between a
minimum and a maximum through Azure Monitor, and that minimum is at least one —
there is no scale-to-zero for an online deployment.

So:

| State | Cost |
| --- | --- |
| Endpoint exists, **zero deployments** | **0** |
| Endpoint exists, one deployment, `instance_count: 1`, **zero requests all month** | **full VM rate, 24/7** |

At `Standard_DS1_v2`, 0.05774 €/hour:

| Window | Cost of an idle deployment |
| --- | --- |
| 1 hour | 0.06 € |
| 1 day | 1.39 € |
| 1 month (730 h) | **42.15 €** |

At `Standard_F2s_v2`, the smallest 2-vCPU alternative: **61.50 €/month** idle.

**42 € per month for an endpoint serving nothing** is the number to remember.
Read the other way, it is reassuring: a two-hour exercise that creates a
deployment, invokes it, and deletes it costs **0.12 €**. The risk is not the
rate, it is the forgetting.

Three details that the exam is fond of:

- **A failed deployment still bills.** *"If you submitted request to create an
  online deployment and it failed, the request might have passed the stage when
  compute is created. In that case, the failed deployment would incur charges."*
  Deleting the endpoint after a failure is part of the exercise, not cleanup
  afterwards.
- **Quota is reserved at 120%.** Azure ML reserves 20% for upgrades:
  `ceil(1.2 × instances) × cores` must be available. One `DS1_v2` instance needs
  2 vCPU of DSv2 quota, not 1. Against a family limit of 6, that is fine. The
  reserved portion *"won't incur cost unless such operations run."*
- `Standard_DS1_v2` is supported for managed online endpoints, with a documented
  caveat: *"Small VM SKUs such as `Standard_DS1_v2` and `Standard_F2s_v2` may be
  too small for bigger models and may lead to container termination due to
  insufficient memory, not enough space on the disk, or probe failure."* For a
  scikit-learn model it is the right choice; if the deployment dies with
  `ResourceNotReady`, that is the reason, and the fix is a bigger SKU rather
  than a retry.

### 4.4 Batch endpoint

> "Invoking a batch endpoint triggers an asynchronous batch inference job. Azure
> Machine Learning automatically provisions compute resources when the job
> starts, and automatically deallocates them as the job completes. This way, you
> only pay for compute when you use it."
>
> "Azure Machine Learning doesn't charge you for batch endpoints or batch
> deployments themselves [...] Use **scale-to-zero** in clusters to ensure no
> resources are consumed when they're idle."
> — [What are batch endpoints?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-batch)

A batch endpoint has no compute of its own. It points at an AmlCompute cluster —
the same object as §4.1, with the same `min_nodes: 0` behaviour. The endpoint,
the deployment, and the cluster at rest are all free; the only charge is the
node-hours the job actually consumes.

### 4.5 Batch against online — the billing difference in one line

Both host a model behind a name. The difference is not the workload shape, it is
**what the meter is attached to**.

| | Managed online endpoint | Batch endpoint |
| --- | --- | --- |
| Meter attached to | instances **assigned to the deployment** | nodes **allocated for the job** |
| Cost proportional to | **wall-clock time the deployment exists** | **work actually done** |
| Idle cost | full rate | zero |
| Scale to zero | no — minimum is 1 instance | yes — that is the normal state |
| Who allocates the compute | the deployment, at creation | the job, at invocation |
| How to stop paying | delete the deployment | nothing to do |

The exam framing: an online endpoint is *provisioned capacity*, a batch endpoint
is *consumed capacity*. Latency is the reason to choose one; the billing model
is the consequence.

---

## 5. Decision table for Weeks 2–5

What to use for which exercise, at what cost, and how to turn it off. This is
the part the next feature spec should consume.

| Exercise | Compute form | Size | Cost | How it stops costing |
| --- | --- | --- | --- | --- |
| MLflow tracking, model registry, notebooks, run comparison | **none — local** | — | **0** | nothing to stop |
| Chunking, embeddings, RAG evaluation, synthetic data (Week 5) | **none — local** | — | **0** | nothing to stop |
| Training script, pipeline, AutoML, hyperparameter sweep | AmlCompute cluster, `min_nodes: 0`, `max_nodes: 1` | `Standard_DS1_v2` | **0 at rest**, 0.05774 €/node-hour running | automatic scale-down; `az ml compute delete` at the end of the week |
| Notebook work that genuinely must run on Azure | compute instance | `Standard_DS1_v2` | 0.05774 €/hour running, **≈ 25 €/month if merely stopped** | **`az ml compute delete` — do not stop it** |
| Batch endpoint, batch scoring | batch endpoint over the same cluster | `Standard_DS1_v2` | job duration only | nothing at rest; delete the endpoint when done |
| Real-time endpoint, safe rollout, blue/green, endpoint troubleshooting | managed online endpoint, `instance_count: 1` | `Standard_DS1_v2` | 0.06 €/hour, **42.15 €/month if left up** | **`az ml online-endpoint delete` in the same session** |
| Distributed training | none — theory only | — | 0 | — |
| Provisioned throughput units (Week 3) | none — theory only | — | 0 | — |

**Budget shape of Week 2.** With the cluster exercises measured in node-hours
and the endpoint exercises deleted the same session, the whole of Week 2 should
land in the range of **1–3 €**. Anything above that means something was left
running, and the thing most likely to have been left running is an online
deployment.

**The single rule that covers all of it**: an online deployment and a compute
instance are the only two objects here that cost money while doing nothing.
Neither should survive the end of the session that created it.

---

## 6. Shutdown procedures

Read-only verification first — this lists every compute object in the workspace,
whatever its state:

```bash
export PATH="/usr/local/bin:$PATH"
az ml compute list -g rg-ai300-test01 -w ai300ml2mgou37pfmjou -o table
az ml online-endpoint list -g rg-ai300-test01 -w ai300ml2mgou37pfmjou -o table
az ml batch-endpoint list -g rg-ai300-test01 -w ai300ml2mgou37pfmjou -o table
```

Deletion, per form:

```bash
# Cluster or compute instance — same command, both forms
az ml compute delete -g rg-ai300-test01 -w ai300ml2mgou37pfmjou \
  -n <compute-name> --yes

# Online endpoint — deletes its deployments with it, which is what stops
# the VM charge. Deleting the endpoint is the operation that matters;
# deleting only the endpoint's traffic rule stops nothing.
az ml online-endpoint delete -g rg-ai300-test01 -w ai300ml2mgou37pfmjou \
  -n <endpoint-name> --yes

# Batch endpoint — the endpoint is free, so this is tidiness, not cost
# control. The cluster underneath is the thing that could cost, and it is
# already at zero nodes.
az ml batch-endpoint delete -g rg-ai300-test01 -w ai300ml2mgou37pfmjou \
  -n <endpoint-name> --yes
```

**Verifying that a deletion actually stopped the money is a separate step from
verifying that the command succeeded.** A green `delete` proves the control
plane accepted the request. Confirm in Cost Management → Cost analysis, filtered
to `rg-ai300-test01`, that the daily figure returns to approximately zero within
24–48 hours. Compare two windows: on this subscription
`az consumption usage list` has previously returned records with a null cost,
and a null is not a zero.

---

## 7. What is not verified

Listed so that none of it is later remembered as fact.

| Claim | Status | How to settle it |
| --- | --- | --- |
| A cluster resting at `min_nodes: 0` incurs no load balancer charge | **still open** — but a load balancer *is* billed while the cluster is warm, and it was torn down after ≈2 h. See § 7.2 | Read Cost Management for a full day at rest, 2026-08-17 or later |
| ~~The load balancer figure in EUR~~ | ✅ **measured 2026-08-16.** Two meters, `Load Balancer · Standard Included LB Rules and Outbound Rules` and `Load Balancer · Standard Data Processed`, plus `Virtual Network · Standard IPv4 Static Public IP`. See § 7.2 | — |
| Whether trial credit remains on this subscription | **unverifiable from these APIs** | Portal → Cost Management → Credits |
| ~~Whether a budget alert exists~~ | ✅ **confirmed 2026-08-15** by the author, in the portal, before the first hourly resource was created. The CLI still cannot see it; that remains a limitation of `az consumption budget list`, not evidence about the budget | — |
| ~~Node-hours are billed from allocation (image pull, provisioning) rather than from script start~~ | ✅ **confirmed 2026-08-16.** Billed 25.0 min against 12.6 min of script time across three jobs — 1.98×. See § 7.2 | — |
| Managed online endpoint quota | **not exposed** — `az ml compute list-usage` shows no online-endpoint bucket, so the allocatable instance count for a deployment is unknown until one is attempted | Attempt the Week 2 deployment; an `OutOfQuota` error names the real limit |
| The two non-zero Azure ML surcharge meters (GPU, PB) apply to v2 workloads | **unverified**, and out of scope — no GPU exercise is planned | — |

### 7.1 What the first real cluster settled — 2026-08-15

Feature 004 deployed `ai300-cpu-cluster` (`Standard_DS1_v2`, dedicated, min 0 /
max 2) and ran three jobs on it. Four things in this note can now be corrected
or narrowed, and one correction is to § 2 rather than to this section.

**Quota is consumed by allocated nodes, not by the declared maximum.** § 2 said
a stopped compute instance keeps its quota, and quoted the documentation phrase
*"unprovisioned nodes contribute to your quota usage"*. Read against a cluster,
that phrase misleads. Measured on both sides:

| Bucket | cluster idle | 1 node allocated | limit |
| --- | --- | --- | --- |
| Total Clusters | 1 | 1 | 200 |
| Total Cluster Dedicated Regional vCPUs | **0** | **1** | 20 |
| Standard DSv2 Family Cluster Dedicated vCPUs | **0** | **1** | 6 |

So a cluster at rest holds **one entry in the cluster-count quota and no vCPU
quota at all**. The compute-instance statement in § 2 is unaffected — it comes
from a different documentation page and concerns a different object — but do not
generalise it to clusters.

**No load balancer resource exists in the resource group.** § 4.1 flagged as
unknown whether a cluster at zero nodes bills one. The physical prerequisite was
checked first: `az resource list` shows **no** `Microsoft.Network/*` resource
and **no** `*-azurebatch-*` object in `rg-ai300-test01`, either at zero nodes or
while a node was running.

The documented `<GUID>-azurebatch-cloudserviceloadbalancer` objects most likely
belong to **VNet-injected** clusters, where the networking lands in the
customer's resource group. This workspace runs with `isolationMode: Disabled`
and no virtual network, so that networking is managed on Microsoft's side.
**That explanation is a hypothesis.** The observation — no such resource here —
is not.

A charge cannot be ruled out from resource absence alone, because existence and
billing are different ledgers. But it makes "no load-balancer charge for this
cluster" the likely answer, and the cost reading over a full day is what decides
it. **Still open.**

**Node-hours: not settled, and now cheap to settle.** Three job runs exist with
known submit and completion times; comparing them against the billed node time
answers the § 7 row about whether billing starts at allocation or at script
start. Worth doing when the cost data lands.

**Cost data lags.** The two-window comparison this note prescribes cannot be run
on the same day as the spend. Cost Management had no 2026-08-15 figures hours
after the jobs completed. Any verification of a day's spend is a next-day
activity — which is a scheduling fact worth having written down, since feature
004's task list got it wrong.

### 7.2 What the measured bill settled — read 2026-08-16, for 2026-08-15

**The headline: the VM meter is 26% of the cost of running a job on this
cluster.** Everything this note priced before today was that 26%.

Three jobs, 12 min 38 s of total script time, on one `Standard_DS1_v2` node.
Estimated from § 3 at **< 0.02 €**. Actually billed **0.0912 €**.

| Meter | € | Share |
| --- | --- | --- |
| Load Balancer · Standard Included LB Rules and Outbound Rules | 0.043925 | 48% |
| Virtual Machines · D1 v2/DS1 v2 | 0.024089 | **26%** |
| Storage · P10 LRS Disk | 0.011014 | 12% |
| Virtual Network · Standard IPv4 Static Public IP | 0.008785 | 10% |
| Load Balancer · Standard Data Processed | 0.001620 | 2% |
| Storage · write / read / list operations | 0.002085 | 2% |
| **Total** | **0.091197** | |

Idle days on either side read **0.000026 €**, so essentially all of it is the
cluster.

**A load balancer is billed for a resource that does not appear in the resource
group.** § 7.1 checked `az resource list` for `Microsoft.Network/*`, found
nothing, and concluded a load-balancer charge was unlikely. The resource check
was right and is still right — re-verified 2026-08-16, still empty — and the
conclusion drawn from it was wrong. The networking sits in a Microsoft-managed
resource group and bills to this one.

> **Existence and billing are different ledgers.** § 7.1 wrote that sentence
> and then reasoned past it. Whether a resource is *visible* in the resource
> group says nothing about whether a meter for it lands on the invoice.

**But the load balancer is torn down, not permanent.** Dividing each meter by
its list rate gives a billed duration — the VM rate is measured (§ 3), the LB
and IP rates are Azure list prices from memory, so those two are **inferences
with an assumed rate**:

| Meter | assumed rate | implied duration |
| --- | --- | --- |
| VM `D1 v2/DS1 v2` | 0.05774 €/h *(measured)* | 25.0 min |
| LB rules | ≈0.021 €/h | ≈2.1 h |
| Static public IP | ≈0.0042 €/h | ≈2.1 h |

The LB and IP agree at ≈2.1 h. The cluster was created 16:38 UTC and the last
node was gone by ≈17:25; 2.1 h reaches ≈18:44, against 7.4 h left in the UTC
day. **The load balancer outlived the nodes by ≈1.5 h and was then removed.**
That is the strongest evidence yet that a cluster at rest is free — but it is
not the full-day reading, so § 4.1's guarantee still awaits 2026-08-17.

**Node-hours are billed from allocation.** Settled, and against script start:

| Measure | total |
| --- | --- |
| Script execution | 12 min 38 s |
| Submission → end | 21 min 09 s |
| Submission → end + 3 × 120 s idle | 27 min 09 s |
| **Billed node time** | **25 min 02 s** |

Provisioning and image pull (≈2 min 50 s per job) are billed, and so is the
120-second idle tail. **A short job costs about twice its script time.** Fewer,
longer jobs are materially cheaper than many short ones.

### The planning rate that replaces § 3 for cluster jobs

§ 3's 0.05774 €/node-hour is the VM meter and is correct as such. For budgeting
a job, split by how the meters actually scale:

| Component | Rate | Scales with |
| --- | --- | --- |
| VM + P10 OS disk | **≈0.082 €/node-hour** | allocated node time, incl. provisioning and idle tail |
| LB rules + public IP | **≈0.025 €/hour** | how long the cluster stays warm (≈2 h tail) |

Do not blend these into one per-node-hour figure: the load balancer does not
scale with node count or node time. For a short job it dominates; for a long one
it is noise.

---

## Sources

- [Online endpoints for real-time inference](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-online)
- [What are batch endpoints?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-batch)
- [What is an Azure Machine Learning compute instance?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-compute-instance)
- [Manage and optimize costs](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-optimize-cost)
- [Plan to manage costs](https://learn.microsoft.com/en-us/azure/machine-learning/concept-plan-manage-cost)
- [View costs for managed online endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-view-online-endpoints-costs)
- [Managed online endpoints VM SKU list](https://learn.microsoft.com/en-us/azure/machine-learning/reference-managed-online-endpoints-vm-sku-list)
- [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
