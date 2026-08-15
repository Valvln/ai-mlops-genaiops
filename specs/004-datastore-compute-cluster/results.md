# Results: what was actually observed

**Feature**: 004 · **Session**: 2026-08-15

Observations, with their commands and their raw output. Where a result
contradicts something this feature wrote down earlier, the contradiction is the
entry — not a quietly corrected sentence.

---

## Deployment

`az deployment group create -g rg-ai300-test01 -f infra/main.bicep`

| | |
| --- | --- |
| Deployment name | `ai300-004-1786811820` |
| State | **Succeeded** |
| Timestamp | 2026-08-15T16:38:39Z |
| Created | container `training-data`, datastore `ai300_training_data`, cluster `ai300-cpu-cluster`, one role assignment |

Confirmed in the deployment history, not inferred from the command's exit code:

```text
Name                  State      Time
ai300-004-1786811820  Succeeded  2026-08-15T16:38:39.010272+00:00
```

Run by the author, not by CI. The CI path is Phase 4 and is still pending.

---

## SC-002 — the cluster rests at zero nodes

**Passed.** Read from the service, not from the template.

`az ml compute show` returned an **empty** `node_state_counts`, which is not a
zero and was not accepted as one. The positive reading came from ARM:

```json
{
  "allocationState": "Steady",
  "current": 0,
  "target": 0,
  "states": {
    "idleNodeCount": 0,      "leavingNodeCount": 0,
    "preemptedNodeCount": 0, "preparingNodeCount": 0,
    "runningNodeCount": 0,   "unusableNodeCount": 0
  }
}
```

Six buckets, all explicitly zero. `az ml compute list-nodes` returned nothing.

Deployed configuration read back: `Standard_DS1_v2`, `dedicated`,
`min_instances: 0`, `max_instances: 2`, `idle_time_before_scale_down: 120`,
`provisioning_state: Succeeded`. The cluster's system-assigned identity exists,
principal `55fa4cc8-2dbe-4db9-bc31-e662e524064d`.

---

## Observation A — was the resource-group grant needed?

**Answer: no. The first compute target was created with no authorisation
failure, while `allowRoleAssignmentOnRG` is `false`.**

The open question in the tracker since feature 002, and it resolves cleanly:

```bash
az resource list -g rg-ai300-test01 --query "[?contains(name,'azurebatch')]" -o table
# (empty)
```

The resource group inventory is **unchanged** by this deployment — the same five
resources plus the Application Insights smart-detection action group. The
cluster and datastore are child resources of the workspace and do not appear at
this level, which is expected.

### The part that did not go as researched

[research.md § R7](./research.md) predicted, from Microsoft's documentation, that
creating a cluster causes three `*-azurebatch-*` objects — a network security
group, a public IP and a load balancer — to be created **in the workspace's
resource group**. That was the mechanism by which the resource-group grant was
expected to matter.

**None of them exists.** At the time of reading, minutes after the cluster was
created and with zero nodes allocated, the resource group contains no Batch
networking resources at all.

The likeliest reading is that these are created when nodes are first allocated
rather than when the cluster is declared — which would make them a property of
running, not of existing. **That is a hypothesis, not a result.** The re-read
while the verification job holds a node is what settles it, and it is recorded
below.

So Observation A is answered, but narrowly: the grant was not needed *to create
the cluster*. Whether it is needed *to allocate a node* is a different question,
and the job is what asks it.

---

## Quota — a documented claim that failed measurement

**This contradicts what this feature's own research wrote down.**

[research.md § R3](./research.md) asserted, reasoning from the documentation
sentence *"unprovisioned nodes contribute to your quota usage"*, that the
cluster would hold 2 vCPU of DSv2 family quota for as long as it existed.

Measured with the cluster deployed and idle:

| Bucket | used | limit |
| --- | --- | --- |
| Total Clusters | **1** | 200 |
| Total Cluster Dedicated Regional vCPUs | **0** | 20 |
| Standard DSv2 Family Cluster Dedicated vCPUs | **0** | 6 |
| Total Cluster Low Priority Regional vCPUs | 0 | **0** |

**No vCPU quota is consumed at zero nodes.** Only the cluster-count bucket
moved. The claim was an inference from a documentation sentence and it was
wrong; the correction is boxed in `research.md` rather than silently edited.

Caveats kept rather than smoothed away: the reading was taken about a minute
after creation and quota accounting may be eventually consistent, and one
reading at one moment is not a behaviour. The reading taken while a node is
allocated is what completes it.

The low-priority row confirms the cost model's finding independently: regional
limit **0**, while the per-family rows report `-1`. The per-family row is the
wrong row to read.

---

## The discriminator — the author cannot read the data

**Established, and this is what gives the job's result meaning.**

The author holds `Owner` on the storage account and **no** blob data-plane role.
Owner is a management-plane role: it confers control over the account and over
who may access it, and no access to the bytes.

The CLI's refusal is a friendly wrapper, and this repository's runbook warns
that a failing `az` command may never have reached Azure. So the refusal was
confirmed against the service directly:

```bash
TOKEN=$(az account get-access-token --resource https://storage.azure.com/ --query accessToken -o tsv)
curl -H "Authorization: Bearer $TOKEN" -H "x-ms-version: 2023-11-03" \
  "https://ai300st2mgou37pfmjou.blob.core.windows.net/training-data/sample.csv"
```

```xml
<Error>
  <Code>AuthorizationPermissionMismatch</Code>
  <Message>This request is not authorized to perform this operation using this permission.
  RequestId:de7d7d8f-601e-0013-5bd5-2c55a1000000
  Time:2026-08-15T16:43:51.7342585Z</Message>
</Error>
```

**HTTP 403, server-side, with a RequestId.** That request reached Azure and was
refused there. It is an authorisation denial and not a client-side failure, a
bad name, or an empty result.

**Consequence**: if the verification job reads the file successfully, it cannot
have done so with the author's credentials. The claim in FR-018 becomes provable
rather than asserted.

The file itself was uploaded with the **account key** (`--auth-mode key`). That
is setup, not a claim: how the bytes arrived is not what is under test.

---

## The readings taken while a node was allocated

Both pending questions above were settled during the verification job, with one
node up and the job `Running`.

### Quota tracks allocated nodes, not declared maximums

| Bucket | at 0 nodes | with 1 node | limit |
| --- | --- | --- | --- |
| Total Clusters | 1 | 1 | 200 |
| Total Cluster Dedicated Regional vCPUs | 0 | **1** | 20 |
| Standard DSv2 Family Cluster Dedicated vCPUs | 0 | **1** | 6 |

**Settled.** Quota moves with allocation and returns when nodes are released. It
is not reserved against `maxNodeCount`. The correction to
[research.md § R3](./research.md) is confirmed by the pair of readings rather
than by the single one — a cluster at rest costs neither money nor vCPU quota.

The exam-relevant statement that survives: *a compute cluster consumes one entry
in the cluster-count quota for as long as it exists, and vCPU quota only while
nodes are allocated.* The documentation sentence about "unprovisioned nodes"
refers to something narrower than this project read into it.

### The Batch networking resources are not in this resource group at all

```bash
az resource list -g rg-ai300-test01 \
  --query "[?contains(name,'azurebatch') || contains(type,'Network')]" -o table
# (empty) — with a node running
```

**Not a timing effect.** [research.md § R7](./research.md) predicted these three
objects would appear in the resource group, and the earlier reading at zero
nodes left open that they might appear on allocation. They do not appear then
either. There are no `*-azurebatch-*` resources and no
`Microsoft.Network/*` resources in this resource group at any point.

The most probable explanation, and it is labelled as such: the documented
`<GUID>-azurebatch-cloudservice*` objects belong to **VNet-injected** clusters,
where the networking sits in the customer's own resource group. This workspace
has `managedNetwork.isolationMode: Disabled` and no virtual network, so the
cluster's networking is managed on Microsoft's side and never lands here.

**This is not verified**, and it is the kind of plausible-sounding mechanism this
repository has already been wrong about twice today. What *is* verified is the
observation: no such resources exist here, at zero nodes or with a node running.

**Consequence for the load-balancer question (R8)**: a load balancer that does
not exist in this resource group cannot produce a charge attributable to it. That
makes "no load-balancer charge for this cluster" the likely answer — but
existence and billing are different ledgers, exactly as quota and cost turned out
to be, so T027's cost reading over a full day still decides it. The prediction is
recorded here so the cost reading can confirm or embarrass it.

---

## SC-003 — the datastore is reachable from the workspace

**Passed.** Job `modest_chayote_c3437h2z1f`, `Completed`.

| | Recorded before the job existed | Logged by the job |
| --- | --- | --- |
| bytes | 164 | **164** |
| sha256 | `498429272d6251d8da130431385c3acfa0be0f47cb172e24370dc350183e2148` | **identical** |
| rows | 5 | **5** |

Raw output from `user_logs/std_log.txt`:

```text
DATASTORE-CHECK-BEGIN
DATASTORE-CHECK path=/mnt/azureml/cr/j/610c57141e0643279cf532afd9fc31fa/cap/data-capability/wd/INPUT_sample/sample.csv
DATASTORE-CHECK bytes=164
DATASTORE-CHECK sha256=498429272d6251d8da130431385c3acfa0be0f47cb172e24370dc350183e2148
DATASTORE-CHECK rows=5
DATASTORE-CHECK-END
```

The mount path shows the file was materialised on a cluster node. The digest
could not have been produced without reading the bytes. And the author cannot
read that blob — established by a server-side 403 above — so the read was
performed by an identity that is not the author's.

That is the full chain FR-018 asked for, and every link is an observation.

### An unplanned confirmation of the discriminator

`az ml job download` **failed**, with the same error as the manual probe:

```text
<Code>AuthorizationPermissionMismatch</Code>
RequestId:8694d8a5-e01e-0040-4dd6-2c7695000000
```

Job logs live in blob storage, so downloading them needs blob data access, which
the author does not have. The logs were read instead with the account key,
directly from `azureml/ExperimentRun/dcid.<job>/user_logs/std_log.txt`.

Worth recording for two reasons. It is a second, independent demonstration that
the author's identity really has no data-plane access — this time unplanned,
which makes it better evidence than the probe designed to produce it. And it is
a practical consequence to know about: on this workspace, reading job logs from
the CLI requires either the account key or a data-plane role grant.

## SC-004 — the cluster returns to zero on its own

**Passed.** Observed mid-transition, with no command issued to cause it:

```json
{"alloc": "Resizing", "current": 1, "target": 0,
 "states": {"leavingNodeCount": 1, "runningNodeCount": 0, "idleNodeCount": 0}}
```

`targetNodeCount` had already dropped to 0 and one node was `leaving`. Both
halves of the criterion are therefore satisfied: the cluster allocated a node
when work arrived (`currentNodeCount` 1 during the job) and released it when the
work ended, driven by the declared 120-second idle interval rather than by an
operator.

---

## SC-008 cannot be settled today, and the plan was wrong to imply it could

The baseline window queried cleanly through the Cost Management query API
(`az consumption usage list` is the one that returns nulls here; this endpoint
returns real figures):

| Day | Services with any cost | Total |
| --- | --- | --- |
| 2026-08-08 | Bandwidth, Key Vault, Storage | ~0.00019 € |
| 2026-08-09 | Bandwidth, Storage | ~0.00030 € |

Sub-cent, and no compute meter — consistent with everything before today.

**But today's own figures are not readable yet.** Azure cost data lags ingestion
by hours, so the two jobs run this afternoon will not appear until tomorrow.
T028 as written — *"comparing two windows… under 1 €"* — therefore cannot be
completed in this session for the window that matters.

This is a defect in the plan, not in the work: **the task list scheduled a cost
verification for a moment when the data does not exist yet.** It is the same
mistake as scheduling the load-balancer reading for today, which the plan *did*
catch and mark deferred. One was noticed, the other was not.

So T028 joins T027 in the next session, and both are carried in the handover
rather than reported as done. What can be said today is bounded and is said that
way: two `DS1_v2` node-runs of a few minutes each, at 0.05774 €/node-hour, is
arithmetically under 0.02 € — **an estimate from the rate card, not a
measurement**, and the distinction is the whole point of the cost model note.

A second reading during this session also returned `429 Too Many Requests`. That
is a server response and not a client-side failure — worth distinguishing,
because this repository's runbook records that a failing `az` command may never
have reached Azure. This one did.

---

## The necessity test — the grant is load-bearing

**This is the result the feature was most at risk of getting wrong, and it came
back the opposite way from the prediction.**

[research.md § R4/D7](./research.md) expected the container grant to be
**inert**. The reasoning: the workspace's managed identity already holds
`Storage Blob Data Contributor` at storage *account* scope, which covers this
container, so something else would authorise the read and the new assignment
would be decoration — the shape feature 002 shipped.

### Withdrawal

Grant deleted, verified absent, job resubmitted. Job `stoic_zoo_rrf7805s9q`
**Failed**, at the data mount:

```text
Failed to mount URI azureml://…/datastores/ai300_training_data/paths/sample.csv
  at mount point …/INPUT_sample
Error Code: ScriptExecution.StreamAccess.Authentication
Native Error: error in streaming from input data sources
  StreamError(PermissionDenied(Some(This request is not authorized to perform
  this operation using this permission.)))
```

And the underlying HTTP exchange, from `rslex.log`:

```text
request_uri=https://ai300st2mgou37pfmjou.blob.core.windows.net/training-data/sample.csv
response_status_code=403
ms_server_side_request_id=Some("df3c1698-401e-0004-7bd8-2cfcaa000000")
```

**An authorisation refusal, server-side, against the exact blob, through the
exact datastore, with a server request id.** It satisfies FR-019: this is not a
bad path, not a missing file, not a client-side failure, and not an empty
result. The job did not "fail" — it was *refused*.

### Restoration

`az deployment group create` re-applied the template, `Succeeded`, and the
assignment is present again. The job was resubmitted rather than the restored
configuration merely inspected — job `willing_vinegar_s7pkrrjkvs`, **Completed**,
with byte count, sha256 and row count identical to the recorded values.

**Both directions were run.** Withdraw → refused with a 403 at the mount.
Restore → the same job reads the same file successfully. That symmetry is what
feature 003's FR-008 asks for, and it is what separates "this grant is
configured" from "this grant is what authorises the read".

Three job runs in total, therefore:

| Job | Grant | Outcome |
| --- | --- | --- |
| `modest_chayote_c3437h2z1f` | present | Completed, checksum matched |
| `stoic_zoo_rrf7805s9q` | **withdrawn** | **Failed** — 403 at the data mount |
| `willing_vinegar_s7pkrrjkvs` | restored | Completed, checksum matched |

### Why the prediction was wrong, which is the useful part

The workspace identity's account-scope grant does not authorise this read
because **the job does not run as the workspace identity**. `job.yml` declares
`identity: managed`, which selects the compute cluster's system-assigned
identity, and that principal held exactly one role assignment: the container
grant. A grant held by one principal does not authorise a read performed by
another.

Stated as the rule worth remembering: **the grant that matters is the one held
by the identity the job actually runs as** — and for a job on a compute cluster
with `identity: managed`, that is the cluster's identity, not the workspace's.
Identity selection is a per-job decision, and it decides which of several
plausible grants is the one doing the work.

This also retires the worry that drove D7. The design was right; the reasoning
offered for doubting it confused *an identity that could have read the data*
with *the identity that did*.

### What this means for the template

The comment in `infra/main.bicep` has been rewritten from "this may be inert"
to what the test established, with the failing job name and the server request
id in it. Two assignments now sit in that template with opposite statuses, each
labelled with the evidence for its label:

| Assignment | Status | Established by |
| --- | --- | --- |
| Key Vault Secrets User → workspace identity | **inert** | Feature 002: the platform grants Key Vault Administrator anyway |
| Storage Blob Data Reader → cluster identity | **load-bearing** | This test: withdraw → 403, restore → passes |

---

## Still open at the end of this entry

| Question | Settled by | Status |
| --- | --- | --- |
| Does the job read the file, and as which identity | The verification job's checksum | ✅ yes, as the cluster's identity |
| Do the `*-azurebatch-*` resources appear when a node allocates | Re-read during the job | ✅ no — they never appear |
| Does vCPU quota track allocated nodes | Re-read during the job | ✅ yes: 0 → 1 → 0 |
| Is the container grant load-bearing or inert | The necessity test | ✅ **load-bearing**, proven both ways |
| Can CI deploy this template, and at what cost in operations | Phase 4, needs the author to push and approve | ❌ **not started** |
| Does a cluster at zero nodes bill a load balancer | Cost reading over a full day, T027 | ⏸ next session |
| What this feature actually cost | Two-window cost comparison, T028 | ⏸ next session — data lags a day |
| Are node-hours billed from allocation or from script start | Compare the three jobs' durations against billed node time | ⏸ next session, and now cheap |

## Final state of the environment

Read at the end of the session, after the third job scaled down:

```json
{"alloc": "Steady", "current": 0, "target": 0,
 "states": {"idleNodeCount": 0, "leavingNodeCount": 0, "preemptedNodeCount": 0,
            "preparingNodeCount": 0, "runningNodeCount": 0, "unusableNodeCount": 0}}
```

| Check | Result |
| --- | --- |
| Cluster nodes | **0**, `Steady`, ~270 s after the last job |
| DSv2 family vCPU quota | back to **0** used |
| Compute objects in the workspace | one: `ai300-cpu-cluster` |
| Compute instances | **none** |
| Online endpoints | **none** |
| Batch endpoints | **none** |

**SC-010 satisfied.** Nothing is left running.

## Scorecard

| Criterion | Status |
| --- | --- |
| SC-001 deployment record succeeded | ✅ by hand; ❌ **not yet via CI** |
| SC-002 cluster at zero nodes, read from the service | ✅ |
| SC-003 job output derived from the file's bytes | ✅ twice |
| SC-004 allocates, then returns to zero unprompted | ✅ |
| SC-005 size within family and regional quota | ✅ measured on both sides |
| SC-006 role operations traced to failing runs | ⏸ Phase 4 not started |
| SC-007 boundary probes still refuse | ⏸ Phase 4 not started |
| SC-008 cost under 1 €, two windows | ⏸ data lags a day |
| SC-009 both observations recorded with dates | ✅ |
| SC-010 nothing left running | ✅ |

Six of ten settled, three deferred to the next session for reasons that are
properties of the data rather than of the work, and one — the CI path — genuinely
not started because it needs the author at the approval gate.
