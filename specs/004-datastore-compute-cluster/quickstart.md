# Quickstart: verifying feature 004

**Feature**: 004 · **Date**: 2026-08-15

The runnable sequence that settles every success criterion in
[spec.md](./spec.md). Read [research.md](./research.md) first if you want to
know *why* each check is shaped the way it is; this file is the *how*.

Every command below is real. Where a command is expected to **fail**, that is
stated and the failure is the evidence — do not "fix" it.

## Prerequisites

```bash
export PATH="/usr/local/bin:$PATH"
cd "/Users/valerioquaranta/Documents/AI-Engineering/Data Science/Development/AI-MLOps-GenAIOps"

RG=rg-ai300-test01
WS=ai300ml2mgou37pfmjou
SA=ai300st2mgou37pfmjou
CLUSTER=ai300-cpu-cluster        # confirm against the deployed name
CONTAINER=training-data
DATASTORE=ai300_training_data
```

The `ml` CLI extension must be installed — see `infra/DEPLOY.md` § 0.1a.

⚠️ **Before the first hourly resource exists**: the budget alert was reconfirmed
in the portal on 2026-08-15. With `spendingLimit: Off` it is the only notice
that exists, and it notifies rather than caps.

---

## 0. Before deploying — the three gates that cost nothing

```bash
az bicep build --file infra/main.bicep --stdout > /dev/null && echo "compiles"

az deployment group what-if \
  -g $RG -f infra/main.bicep --no-pretty-print
```

`what-if` is the gate `az bicep build` cannot be: region eligibility, name
length limits and quota are invisible to the compiler. Expect exactly four
`Create` entries — container, datastore, compute, role assignment — and
`NoChange` or `Ignore` for everything else. **A `Modify` on an existing resource
is a defect**: this feature adds, it does not alter.

---

## 1. SC-002 — the cluster rests at zero nodes

The criterion the specification warns against faking. Read the **service**, not
the template.

```bash
az ml compute show -g $RG -w $WS -n $CLUSTER \
  --query "{state:provisioning_state, size:size, tier:tier, \
            min:min_instances, max:max_instances, \
            idle:idle_time_before_scale_down, \
            current:current_node_count, running:running_node_count}" -o json
```

Passes when: `current_node_count` and `running_node_count` are **0**, `state` is
`Succeeded`, `tier` is `dedicated`.

Also read the raw node counts, which is where a node that is preparing or
leaving shows up and the summary may not:

```bash
az ml compute list-nodes -g $RG -w $WS -n $CLUSTER -o table   # expect: empty
```

> **What does not count**: `min_instances: 0` in this output is the template's
> request read back. It is not evidence that no node is allocated. The node
> counts are.

---

## 2. Observation A — was the resource-group grant needed?

Available the moment the cluster exists. See [research.md § R7](./research.md).

```bash
az resource list -g $RG --query "[?contains(name, 'azurebatch')].{name:name, type:type}" -o table
```

| Outcome | Record it as |
| --- | --- |
| Three `*-azurebatch-*` resources exist (NSG, public IP, load balancer) and the cluster is `Succeeded` | The withdrawn resource-group grant was **not** needed for the first compute. |
| Cluster creation failed with an authorisation error | The grant **was** load-bearing. Quote the error verbatim; `infra/DEPLOY.md` already names the remedy. |

Write down the date either way. An expectation recorded as a result does not
discharge FR-016.

---

## 3. The discriminator — the author cannot read this data

Run **before** the job, because it is what makes the job's success meaningful.

```bash
# Setup: put the known file there, using the account key.
# This is setup, not a claim: how the file arrives is not what is being tested.
az storage blob upload \
  --account-name $SA --container-name $CONTAINER \
  --name sample.csv --file mlops/datastore-check/sample.csv \
  --auth-mode key --overwrite

# THIS COMMAND IS EXPECTED TO FAIL. Capture the error verbatim.
az storage blob download \
  --account-name $SA --container-name $CONTAINER \
  --name sample.csv --file /tmp/should-not-work.csv \
  --auth-mode login
```

Expect `AuthorizationPermissionMismatch`. The author holds `Owner`, which is a
management-plane role and confers **no** blob data access — the same control
plane / data plane split as Key Vault, on a different service.

**Why this matters**: it means a successful read by the job cannot have been
performed with the author's credentials. Without this step, a green job would be
consistent with identity passthrough and would prove nothing about the
workspace's access.

If this command unexpectedly **succeeds**, the discriminator is gone: stop, find
out which data-plane role the author acquired, and re-establish the test before
reading anything into the job's result.

---

## 4. SC-003 — the datastore is reachable, proven by a checksum

```bash
# The known file's identity, recorded before the job runs
shasum -a 256 mlops/datastore-check/sample.csv
wc -c < mlops/datastore-check/sample.csv

az ml job create -g $RG -w $WS -f mlops/datastore-check/job.yml --stream
```

While it runs, confirm the cluster actually allocated — the other half of SC-004:

```bash
az ml compute list-nodes -g $RG -w $WS -n $CLUSTER -o table   # expect >= 1 node
```

Passes when the job reaches `Completed` **and** its logged sha256 and byte count
equal the values above.

> **What does not count**: a `Completed` job. The specification's edge case is
> explicit — a job that starts, logs and exits zero would satisfy a naive check
> while proving nothing. The checksum is the evidence; the exit status is not.

---

## 5. SC-004 — it goes back to zero on its own

```bash
sleep 200   # 120 s idle interval plus margin
az ml compute list-nodes -g $RG -w $WS -n $CLUSTER -o table   # expect: empty
```

Passes when the node list is empty **without any command having been run to
make it so**. A cluster scaled down by hand demonstrates the operator, not the
configuration.

---

## 6. D7 — is the container grant load-bearing, or decoration?

The check that stops this feature repeating feature 002's outcome. See
[data-model.md § 4](./data-model.md).

```bash
CONTAINER_ID=$(az storage account show -n $SA -g $RG --query id -o tsv)/blobServices/default/containers/$CONTAINER
CLUSTER_MI=$(az ml compute show -g $RG -w $WS -n $CLUSTER --query "identity.principal_id" -o tsv)

az role assignment list --scope "$CONTAINER_ID" \
  --query "[?principalId=='$CLUSTER_MI'].{role:roleDefinitionName, name:name}" -o table

# Withdraw it, then re-run the job
az role assignment delete --scope "$CONTAINER_ID" \
  --assignee-object-id "$CLUSTER_MI" --role "Storage Blob Data Reader"

az ml job create -g $RG -w $WS -f mlops/datastore-check/job.yml --stream
```

| Second run | Conclusion | What to do |
| --- | --- | --- |
| **Fails** on authorisation | The grant is load-bearing and the cluster identity is the reader | Redeploy `main.bicep` to restore it, confirm the job passes again, say so in the template comment |
| **Succeeds** | The grant is **inert** — the workspace identity's account-scope grant is doing the work | Say so plainly in the template comment, exactly as `main.bicep` already does for its Key Vault assignment, or delete the assignment |

Whichever happens, the template must not be left claiming something the test
disproved. Restore the deployed state with `az deployment group create` before
moving on.

---

## 7. SC-008 and SC-010 — cost, and nothing left running

```bash
az ml compute list -g $RG -w $WS -o table
az ml online-endpoint list -g $RG -w $WS -o table    # expect: empty
az ml batch-endpoint list -g $RG -w $WS -o table     # expect: empty
az ml compute list-nodes -g $RG -w $WS -n $CLUSTER -o table   # expect: empty
```

Then Cost Management → Cost analysis, scoped to `rg-ai300-test01`, **comparing
two windows** — the days before this feature against the days spanning it.

> `az consumption usage list` has returned records with a null cost on this
> subscription. **A null is not a zero**, and one window is not a comparison.

Passes when the delta is under 1 € and consists only of virtual machine
node-hours for the minutes the two jobs ran.

---

## 8. Observation C — the load balancer question, next session

Not available today: it needs a full day of the cluster resting at zero nodes.
[research.md § R8](./research.md) explains why the documentation does not settle
it.

```bash
# Does the object exist while the cluster rests at zero? (available now)
az resource list -g $RG --query "[?type=='Microsoft.Network/loadBalancers'].name" -o table
```

Then, 24–48 hours later, read Cost Management filtered to `rg-ai300-test01` and
look for a **Load Balancer** service line on a day when no job ran.

| Outcome | Consequence |
| --- | --- |
| No load balancer meter | A cluster at zero nodes really is free at rest. The shutdown procedure stays "leave it". |
| A load balancer meter, ~0.30 €/day | A cluster is **not** free at rest. `docs/exam-notes/compute-cost-model.md` § 7 gets its answer, and the procedure becomes "delete the cluster at the end of the week". |

Update the cost model's § 7 table either way — that section exists so unverified
claims are never later remembered as facts.

---

## If something goes wrong

| Symptom | Most likely cause |
| --- | --- |
| Deployment red with `AuthorizationFailed` | Expected. Read which operation it names; see [contracts/role-additions.md](./contracts/role-additions.md). Do not widen the role beyond it. |
| Job fails on quota at allocation | Quota is checked when a node is requested, not when the cluster is created. Confirm with `az ml compute list-usage -g $RG -w $WS -o table`. |
| Job fails reading the input | The datastore, the grant, or the job's identity. Check in that order; § 3 has already established that the author's own identity is not the reader. |
| `az` says `No subscriptions found` | Client-side. The CLI resolves the subscription from a local cache and never reached Azure. Not an authorisation refusal. |
| The workflow is green but nothing changed | Green is not proof that something deployed. `az deployment group list -g $RG -o table` is. |
