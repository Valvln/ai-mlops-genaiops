# Quickstart — validating the reduction

How to prove this feature did what it claims. Read
[contracts/role-assignments.md](contracts/role-assignments.md) for the exact
commands; this document is the sequence and what each step has to show.

**Cost**: zero. Role assignments are not billed and no resource changes tier.

**Prerequisites**:

```bash
export PATH="/usr/local/bin:$PATH"
az extension add --name ml --yes    # free, local; remove with: az extension remove -n ml
```

Authority to create and remove role assignments is required — Owner or User
Access Administrator. Contributor is not enough. Verified present for this
subscription.

---

## Before touching anything — capture the baseline

Three things must be recorded first, because two of them are needed to verify
the result and one of them cannot be reconstructed afterwards.

```bash
RG=rg-ai300-test01
MI=85e8321f-1e51-42cb-8ced-7fca9b51498b

# 1. The four grants, with the names needed to remove them
az role assignment list --all --assignee "$MI" \
  --query "[].{name:name, role:roleDefinitionName, scope:scope}" -o json \
  > /tmp/ai300-grants-before.json

# 2. The service's own view of its dependencies
az ml workspace diagnose --name ai300ml2mgou37pfmjou --resource-group "$RG"

# 3. The resource count, to prove later that nothing was created
az resource list -g "$RG" --query "length(@)"
```

Expected: four grants, all-empty diagnose arrays, and `5`.

---

## Step 1 — local build

```bash
az bicep build --file infra/main.bicep
```

Exit 0 and **no output**. Anything printed is a finding — stop.

This proves the template compiles. It proves nothing about whether it deploys;
feature 001 shipped two defects that compiled without a warning.

---

## Step 2 — dry run

```bash
az deployment group what-if -g "$RG" --template-file infra/main.bicep
```

| Check | Expected |
| --- | --- |
| Role assignments to create | **2** |
| Anything else to create | **0** |
| Resources to delete | **0** |
| Resources to modify | **0** |
| Anything mentioning a container registry or compute | absent |

A permission grant is a resource in the dry run's output, so the two grants
*will* appear under Create. That is the change working, not a violation of
SC-002 — what must be zero is everything else.

If the dry run wants to modify one of the five resources, the template drifted —
stop and find out why before deploying.

Note the limit already learned in feature 001: the dry run renders what the
template declares. It cannot show a grant the platform intends to add on its
own.

---

## Step 3 — the ordering that keeps the gaps short

The order matters. See [data-model.md](data-model.md) for why.

1. Delete the platform's blob grant. **This opens the only unavoidable gap** —
   the identity has no blob access until step 2 finishes.
2. Deploy the template. Creates both declared grants; the gap closes.
3. Delete the vault administration grant, the file share grant, and the
   resource-group grant.
4. Verify (below).

Never end a session between steps 1 and 2.

---

## Step 4 — verify the permissions

```bash
# SC-004: exactly two grants remain
az role assignment list --all --assignee "$MI" --query "length(@)"

# SC-003: none of them is scoped above a single resource
az role assignment list --all --assignee "$MI" \
  --query "[].{role:roleDefinitionName, scope:scope}" -o table

# SC-007: still five resources, unchanged
az resource list -g "$RG" --query "[].name" -o tsv | sort

# SC-008: redeploying changes nothing
az deployment group what-if -g "$RG" --template-file infra/main.bicep
```

Expected: `2`; two rows, both ending in a resource name rather than in the
resource group; the same five names as before; and a dry run reporting no
change.

---

## Step 5 — prove the identity still works, and that the proof means something

This is the step that is easy to fake and therefore the one to be careful with.
**A command you run yourself proves nothing here** — the author holds Owner, so
it would succeed whether or not the identity kept a single permission.

### 5a — the service-side probe

```bash
az ml workspace diagnose --name ai300ml2mgou37pfmjou --resource-group "$RG"
```

The arrays should still be empty, matching the baseline.

### 5b — the negative control, without which 5a is worthless

An empty result only means something if a *missing* permission would make it
non-empty. SC-006 asks for proof against the storage account **and** the secret
store, so this runs **twice — once per declared grant**:

| Grant withheld | Array that should become non-empty |
| --- | --- |
| blob data access on the storage account | `storageAccountResults` |
| secret read on the key vault | `keyVaultResults` |

For each one, in turn:

1. Remove the declared grant.
2. Re-run `diagnose` and record whether its matching array became non-empty.
3. Re-create the grant by redeploying the template.
4. Confirm the probe is clean again — **before** moving to the other grant.

**Interpreting the outcome — record a verdict per permission, not one for both:**

| Observation | What it means | What to do |
| --- | --- | --- |
| The probe reports a problem while the grant is absent, and is clean once restored | The probe is sensitive to this permission. 5a is real evidence for it. | Record it and move on. |
| The probe stays clean with the grant absent | The probe does not test this permission. **5a proves nothing about it** and cannot be quoted as a pass. | Say so plainly. Report that half of SC-006 as unverified with the reason, per FR-004a. |

**SC-006 is satisfied only if both halves are.** The vault half is the more
likely to come back unverifiable: with no credential-carrying datastore or
connection in existence, there may be no operation at this stage that makes the
service read a secret at all. That is the case FR-004a anticipates — report it
as a limit of the verification rather than substituting a command that looks
like proof.

Step 3 is not optional, in either pass. The environment must be left working
(SC-011).

### 5c — the control-plane probe, and how to read its failure

```bash
az ml workspace sync-keys --name ai300ml2mgou37pfmjou --resource-group "$RG"
```

This makes the service fetch keys from its dependent resources, which needs a
control-plane action on the storage account that the removed resource-group
grant used to cover and that blob data access does not.

**If it fails, that is expected and is not by itself a reason to restore
anything.** Nothing in this project consumes `sync-keys`; under FR-004 a
capability with no consumer does not justify a permission. Record it as a
finding for the author. FR-016 restoration is for something the environment
actually *does* breaking — not for something it merely *could* do becoming
unavailable.

---

## If something needed is missing

Restore first, investigate second (FR-016). The restore commands are in
[contracts/role-assignments.md](contracts/role-assignments.md), one per removed
grant. Then record which operation failed and which permission covered it, and
stop for the author to decide. Do not re-grant and then write the justification
to match — that inverts FR-004.

---

## Known places a failure is expected later

Not defects. Written down so they are recognised rather than diagnosed from
scratch.

| When | What will fail | Restore |
| --- | --- | --- |
| A compute target mounts `workspacefilestore` or `workspaceworkingdirectory` | file share access | the file share grant |
| The workspace provisions compute, a registry, or an endpoint on demand | resource-group authority | the resource-group grant |
| A credential-carrying datastore or connection is created | writing a secret to the vault | widen to secret write, rather than restoring vault administration |
| The first job emits telemetry | metrics publication | grant it then, with a stated need |
