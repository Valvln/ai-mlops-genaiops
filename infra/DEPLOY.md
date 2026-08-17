# Deploying `main.bicep` — runbook

This runbook was written before the first deployment and revised immediately
after it. Steps are still written as instructions so the sequence can be
repeated, but every expected value below is now an observed one.

**Subscription**: Azure subscription 1 (`5900fbc9-a139-49ed-9987-ba560c147eb7`)
**Signed in as**: ValerioQuaranta@Valvln.onmicrosoft.com
**Template region default**: `northeurope` — see "Region eligibility" below
**First deployment**: `ai300-ml-workspace-001`, resource group
`rg-ai300-test01`, succeeded in 69 seconds

Read the "One-way doors" section before running anything. One of the choices
baked into the template cannot be undone for 90 days.

---

## 0. Pre-flight (do this first — it is not optional)

### 0.1 Register the resource providers

All five providers this template needs started out **NotRegistered** on this
subscription. A deployment against an unregistered provider fails immediately
with `MissingSubscriptionRegistration`.

```bash
export PATH="/usr/local/bin:$PATH"

for ns in Microsoft.Storage Microsoft.KeyVault Microsoft.OperationalInsights \
          Microsoft.Insights Microsoft.MachineLearningServices; do
  az provider register --namespace "$ns"
done
```

### 0.1a The `ml` CLI extension

Needed for anything that asks the workspace about itself — `az ml workspace
diagnose`, `az ml datastore list`. Free, local, and kept installed: the exercises
from here on use it constantly.

```bash
az extension add --name ml --yes    # remove with: az extension remove -n ml
```

Registration is free and asynchronous. Wait until all five report `Registered`:

```bash
for ns in Microsoft.Storage Microsoft.KeyVault Microsoft.OperationalInsights \
          Microsoft.Insights Microsoft.MachineLearningServices; do
  printf "%-38s %s\n" "$ns" \
    "$(az provider show --namespace "$ns" --query registrationState -o tsv)"
done
```

All five reached `Registered` in under a minute — faster than the "few minutes
per provider" this runbook originally assumed. Registration is already done for
this subscription and does not need repeating.

**Portal equivalent**: Subscriptions → *Azure subscription 1* → Settings →
Resource providers → search each namespace → Register.

### 0.2 Region eligibility — check before anything else

**`westeurope` does not work on this subscription.** Every resource is rejected:

```text
RequestDisallowedByAzure - Resource '...' was disallowed by Azure:
The selected region is currently not accepting new customers:
https://aka.ms/locationineligible
```

This is a capacity restriction Azure applies to new subscriptions, not a fault
in the template. It is why the template default is now `northeurope`.

Confirmed by `what-if` against this subscription:

| Region | Result |
| --- | --- |
| `westeurope` | blocked — not accepting new customers |
| `northeurope` | OK — **in use** |
| `swedencentral` | OK |
| `italynorth` | OK |

To re-test after changing anything, sweep candidate regions with `what-if`,
which is free and creates nothing:

```bash
for r in northeurope swedencentral italynorth; do
  out=$(az deployment group what-if --resource-group rg-ai300-test01 \
          --template-file infra/main.bicep --parameters location=$r \
          --no-pretty-print 2>&1)
  echo "$out" | grep -q "RequestDisallowedByAzure" \
    && printf "%-16s BLOCKED\n" "$r" || printf "%-16s ok\n" "$r"
done
```

### 0.3 Create the resource group

The name is an input to every generated resource name — see the 90-day trap
below. `rg-ai300-test01` was chosen deliberately as a throwaway name so a
redeploy can move to `-test02` without waiting out a soft-delete window.

```bash
az group create --name rg-ai300-test01 --location northeurope
```

The resource group's own location is only metadata — resources are created in
whatever `location` the template resolves to. Keeping the two the same avoids
having to explain the discrepancy later.

**Portal equivalent**: Resource groups → Create → Subscription *Azure
subscription 1*, Name `rg-ai300-test01`, Region *North Europe* → Review +
create.

### 0.4 Rebuild and confirm the template still compiles

```bash
az bicep build --file infra/main.bicep
```

Expect exit 0 and **no output**. Anything printed here is a finding — stop and
resolve it before deploying.

Note that compiling clean is necessary but not sufficient: the two defects found
during the first deployment (see "Defects found on first deployment") both
compiled without a single warning. Bicep type-checks the schema; it does not
check resource-name length limits or region availability. Only `what-if` against
the live subscription catches those.

---

## One-way doors

These are irreversible or reversible only after a long wait. They are a
consequence of decisions already made in the template, not of the deployment
command.

### The Key Vault name is locked for 90 days once deployed

The vault sets `enablePurgeProtection: true`. That flag **cannot be turned off**
once the vault exists. If the vault is later deleted, it enters a 90-day
soft-delete retention during which it **cannot be purged** and its name **cannot
be reused**.

The trap is specific and easy to walk into. Vault names in this template are
derived from `uniqueString(resourceGroup().id)`, and `resourceGroup().id` is
`/subscriptions/<sub>/resourceGroups/<name>`. Deleting the resource group and
recreating it **with the same name in the same subscription** produces the
identical hash, therefore the identical vault name — which is still held by the
soft-deleted, unpurgeable vault.

The hash depends only on subscription and resource group name. It does **not**
depend on region, so changing region does not sidestep this.

**Consequence**: tear down `rg-ai300-test01` today and redeploy to
`rg-ai300-test01` next week, and the deployment fails on the Key Vault.

**Mitigation in force**: the throwaway resource group name. `ai300kv2mgou37pfmjou`
is now held for 90 days after any teardown; a redeploy would use
`rg-ai300-test02`, which hashes differently.

### Machine learning workspace soft-delete

Azure ML workspaces are also subject to soft-delete, with the workspace name
held for a retention period after deletion. Treat workspace names the same way
as vault names: assume reuse is blocked for a while.

### Provider registration

Registering a provider is effectively permanent for the subscription. It is
harmless and free — noted only for completeness.

---

## 1. Dry run — `what-if`

Never run the deployment before this. `what-if` resolves every expression
against the live subscription and shows what Azure will create, without creating
anything. It is also the only pre-deployment step that catches region
ineligibility and invalid resource names.

```bash
az deployment group what-if \
  --resource-group rg-ai300-test01 \
  --template-file infra/main.bicep
```

**What to check in the output**:

| Check | Expected | First run |
| --- | --- | --- |
| Number of resources to `+ Create` | exactly 5 | ✅ 5 |
| Container registry | absent from the whole output | ✅ absent |
| Any compute resource | absent | ✅ absent |
| ML workspace `sku` | `Basic` / `Basic` | ✅ |
| ML workspace `identity.type` | `SystemAssigned` | ✅ |
| `managedNetwork.isolationMode` | `Disabled` | ✅ |

**On `managedNetwork`**: an earlier version of this runbook expected `what-if`
to reveal the service default for this property. It does not. `what-if` renders
what the template declares plus what it can resolve; defaults applied by the
resource provider at creation time are invisible to it, so leaving the property
unset means going in blind.

That is why the template now declares `isolationMode: 'Disabled'` explicitly.
The property shows up in `what-if` because it is declared, not because the
service revealed anything. The stake is real: `AllowOnlyApprovedOutbound`
provisions a managed Azure Firewall billed hourly regardless of use, which would
dominate the cost of everything else here combined.

**Portal equivalent**: there is no true `what-if` in the portal deployment
blade. It validates the template and shows a Review page, which is weaker. Run
`what-if` from the CLI even if you intend to deploy from the portal.

---

## 2. Deploy

```bash
az deployment group create \
  --resource-group rg-ai300-test01 \
  --template-file infra/main.bicep \
  --name ai300-ml-workspace-001
```

Naming the deployment (`--name`) makes it addressable afterwards; without it you
get a timestamped name that is awkward to reference.

The first run took **69 seconds** — faster than the "several minutes" originally
expected.

### Portal equivalent

The portal deploys ARM JSON, not Bicep, so it consumes the compiled
`infra/main.json` — produced by `az bicep build`, gitignored but present
locally.

1. Portal → search **Deploy a custom template**
2. **Build your own template in the editor**
3. **Load file** → select `infra/main.json`
4. **Save**
5. Subscription *Azure subscription 1*, Resource group `rg-ai300-test01`
6. Leave every parameter at its default — they generate the names
7. **Review + create** → **Create**

The CLI path is preferable here: it deploys the source of truth directly, while
the portal path deploys a build artifact you have to remember to regenerate
after every template change.

---

## 3. Verify

```bash
# Deployment succeeded and produced the expected outputs
az deployment group show \
  --resource-group rg-ai300-test01 \
  --name ai300-ml-workspace-001 \
  --query "{state:properties.provisioningState, outputs:properties.outputs}"

# Exactly 5 resources, and nothing unexpected alongside them
az resource list --resource-group rg-ai300-test01 \
  --query "[].{name:name, type:type, location:location}" -o table

# The three properties that carry cost or security consequences
az resource show \
  --resource-group rg-ai300-test01 \
  --name ai300ml2mgou37pfmjou \
  --resource-type Microsoft.MachineLearningServices/workspaces \
  --api-version 2026-05-01 \
  --query "{identity:identity, managedNetwork:properties.managedNetwork, \
            containerRegistry:properties.containerRegistry}"
```

**The check that matters most**: no container registry appears. If one does, the
workspace provisioned it despite the template — investigate before doing
anything else, because that is a recurring charge.

**On the row count**: this runbook originally said the list must return exactly
**5**. It returns **6**. The sixth is `Application Insights Smart Detection`, a
`microsoft.insights/actiongroups` resource the platform created by itself at
17:06 on 2026-08-07 — ten minutes after the workspace, and declared by no
template. It notifies through ARM roles with no SMS or voice receivers, so it
carries no charge.

Two things worth taking from it. First, the count was never the real check;
*which* resources appear is. Second, the platform adding resources behind the
template is not a one-off — it did the same thing with role assignments, which
is what feature 002 exists to deal with.

### Observed on the first deployment

| Resource | Name |
| --- | --- |
| Storage account | `ai300st2mgou37pfmjou` |
| Key Vault | `ai300kv2mgou37pfmjou` |
| Log Analytics workspace | `ai300law2mgou37pfmjou` |
| Application Insights | `ai300appi2mgou37pfmjou` |
| ML workspace | `ai300ml2mgou37pfmjou` |

- `containerRegistry: null` — nothing was provisioned behind the template's back
- `managedNetwork.isolationMode: "Disabled"`, `enableFirewallLog: false` — no
  managed firewall
- `identity.principalId: 85e8321f-1e51-42cb-8ced-7fca9b51498b` — future role
  assignments attach to this
- `changeableIsolationModes: [AllowInternetOutbound, AllowOnlyApprovedOutbound]`
  — `Disabled` is not a dead end; either isolation mode can still be adopted

**Portal equivalent**: Resource group `rg-ai300-test01` → Overview lists the
resources; Settings → Deployments → `ai300-ml-workspace-001` → Outputs shows the
four output values.

---

## Defects found on first deployment

Both were latent in a template that compiled cleanly and had passed CI. Neither
was reachable without deploying against a live subscription.

### Storage account name exceeded the 24-character cap

`ai300storage` (12) + `uniqueString()` (13) = 25 characters, against a hard cap
of 24:

```text
AccountNameInvalid - ai300storage2mgou37pfmjou is not a valid storage account
name. Storage account name must be between 3 and 24 characters in length and
use numbers and lower-case letters only.
```

Fixed by shortening the prefix to `ai300st` (20 characters total), matching the
abbreviated convention already used by the other four resources.

Why it survived review: `research.md` R5 checked the length of the **ML
workspace** name (20 characters, within its 3–33 limit) and generalised from
there. The storage account has the tightest limit of the five and was never
checked against it. Bicep does not validate name length, and the `westeurope`
rejection fired first and masked the error.

Current margins, worth re-checking whenever a prefix changes:

| Resource | Prefix | Total | Limit |
| --- | --- | --- | --- |
| Storage account | `ai300st` | 20 | 24 |
| Key Vault | `ai300kv` | 20 | 24 |
| Log Analytics | `ai300law` | 21 | 63 |
| Application Insights | `ai300appi` | 22 | 260 |
| ML workspace | `ai300ml` | 20 | 33 |

### `managedNetwork` was left to an unseen service default

Covered in section 1. Now declared explicitly.

---

## Workspace identity permissions

Added by feature 002. The workspace has a system-assigned managed identity
(`principalId` recorded in section 3). What that identity is allowed to do is
**not** something the workspace deployment alone decides — the platform grants
it permissions of its own accord, and none of them appears in the template.

### What the platform granted by itself

Observed on 2026-08-07, all four created by a platform service principal at
workspace creation, with random assignment names:

| What it allowed | Scope | Kept? |
| --- | --- | --- |
| Wildcard control over the vault and the storage account, management of container registries, and writing resource groups | **whole resource group** | removed |
| Read and write of blob data | storage account | kept, now declared in the template |
| Privileged read and write of file shares | storage account | removed |
| Full management of the vault, including who else may access it | key vault | replaced by secret **read** only |

### What it holds now — and why the reduction did not work

**Seven grants, not two.** The attempt to reduce them failed, and how it failed
is the most useful thing in this section.

| Role | Scope | Owner |
| --- | --- | --- |
| Azure AI Administrator | storage account | platform |
| Azure AI Administrator | key vault | platform |
| Azure AI Administrator | Application Insights | platform |
| Storage Blob Data Contributor | storage account | platform |
| Storage File Data Privileged Contributor | storage account | platform |
| Key Vault Administrator | key vault | platform |
| Key Vault Secrets User | key vault | **`main.bicep`** |

Only the last one is declared in the template. The other six are the platform's,
and they cannot be taken away.

#### The platform recreates what you delete

Deleting the blob grant caused the platform to recreate it, under a new random
name, **within the same deployment** — seconds later, by the assignment
timestamps. The template's own declaration of the same permission was then
rejected as a duplicate (`RoleAssignmentExists`), which is why blob access is
not declared in `main.bicep`: declaring it guarantees that every future
deployment fails.

#### `allowRoleAssignmentOnRG: false` relocates authority, it does not reduce it

Setting it removed the single `Azure AI Administrator` grant at resource-group
scope — and the platform immediately created **three** `Azure AI Administrator`
grants, one on each dependent resource. The authority is the same. Only its
shape on paper changed.

This is worth dwelling on: the success criterion "no grant above a single
resource" now **passes**, while the thing it was written to guarantee is no
closer than before. A criterion can be satisfied by a change that defeats its
purpose.

#### What this means for least privilege

While the workspace uses a **system-assigned** identity, the platform maintains
that identity's permissions and will restore what it needs. Least privilege is
not reachable by deleting grants.

The direction worth investigating — **not yet tested, do not assume it works** —
is a **user-assigned** managed identity, which the platform does not create and
may therefore not auto-grant to. That is a separate piece of work.

### Putting a permission back

**In the event, nothing stayed removed** — the platform restored what it wanted
and no grant needed manual restoring. The commands below were written before the
attempt and are kept because they are still the way back if a grant is ever
removed and *not* recreated, and because the two properties this feature did
change are reverted the same way.

Nothing below depends on a value that is not written here.

```bash
export PATH="/usr/local/bin:$PATH"
RG=rg-ai300-test01
MI=85e8321f-1e51-42cb-8ced-7fca9b51498b

SA=$(az storage account show -n ai300st2mgou37pfmjou -g $RG --query id -o tsv)
KV=$(az keyvault show -n ai300kv2mgou37pfmjou -g $RG --query id -o tsv)
RGID=$(az group show -n $RG --query id -o tsv)

# 1. Resource-group-wide authority — needed if the workspace must provision
#    compute, a container registry, or an endpoint on demand
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure AI Administrator" --scope "$RGID"

# 2. File share access — needed as soon as a compute target mounts
#    workspacefilestore or workspaceworkingdirectory
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage File Data Privileged Contributor" --scope "$SA"

# 3. Vault administration — needed only to manage vault access itself. If the
#    need is merely to WRITE secrets, widen the declared grant to
#    "Key Vault Secrets Officer" in main.bicep instead of running this.
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Administrator" --scope "$KV"
```

`--assignee-object-id` with an explicit principal type is used rather than
`--assignee`, which resolves the principal through a directory lookup a
non-administrator may not be allowed to perform.

**If a deployment fails after the blob grant was removed**, the template would
normally recreate it. Re-running the deployment is the first thing to try. If
the template itself is the problem, put the grant back by hand and sort the
template out afterwards — do not leave the workspace without it:

```bash
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "$SA"
```

### Where a failure is expected later

These are not defects. They are written down so a future failure is recognised
in seconds rather than diagnosed from scratch.

| When | What fails | What to do |
| --- | --- | --- |
| ~~The workspace needs authority over the resource group as a whole~~ | **Did not happen. Tested 2026-08-15** — see below | — |
| A job or datastore operation is refused on the storage account | the switch from account keys to identity | check the identity's blob access first; the fallback is `systemDatastoresAuthMode: 'accesskey'` |
| A credential-carrying datastore or connection is created | writing a secret to the vault | the platform's vault administration grant already covers it; only relevant if that grant is ever narrowed |

The three permission-restore commands above are no longer expected to be needed:
the platform maintains those grants itself. They are kept for the case where it
stops doing so.

#### The resource-group grant was not needed — settled 2026-08-15

This section predicted that withholding resource-group-scoped authority would
eventually block the workspace from provisioning compute. **Feature 004 created
the first compute target and nothing was refused.**

```text
az deployment group create -g rg-ai300-test01 -f infra/main.bicep
  → Succeeded (ai300-004-1786811820), with allowRoleAssignmentOnRG still false
```

The cluster was created, allocated nodes for three jobs, and scaled back down,
all without the grant that feature 002 removed. The open question the tracker
has carried since then is closed: **the withdrawn authority is not required for
an AmlCompute cluster on this workspace.**

The predicted *mechanism* was also wrong, and that part is worth keeping. The
expectation — taken from Microsoft's compute cluster documentation — was that
creating a cluster would create three objects in this resource group:
`<GUID>-azurebatch-cloudservicenetworksecuritygroup`,
`<GUID>-azurebatch-cloudservicepublicip`, and
`<GUID>-azurebatch-cloudserviceloadbalancer`.

**None of them exists**, at zero nodes or with a node running:

```bash
az resource list -g rg-ai300-test01 \
  --query "[?contains(name,'azurebatch') || contains(type,'Network')]" -o table
# (empty)
```

The likely reason — **hypothesis, not a result** — is that those objects belong
to VNet-injected clusters, where the networking sits in the customer's resource
group. This workspace has `managedNetwork.isolationMode: Disabled` and no
virtual network, so the cluster's networking never lands here. If a future
feature enables network isolation, expect this to change, and expect the
resource-group authority question to reopen with it.

Do **not** read this as "compute never needs resource-group authority". It is
one cluster, on one workspace, with managed networking disabled.

---

## 4. Cost

**At rest, this deployment should cost approximately nothing.** None of the five
resources carries a fixed monthly fee:

| Resource | Billing model | At this usage |
| --- | --- | --- |
| Storage account (`Standard_LRS`) | per GB stored | empty — negligible |
| Key Vault (standard) | per 10k operations | idle — negligible |
| Log Analytics workspace | per GB ingested, free monthly allowance | well inside it |
| Application Insights | ingestion billed via Log Analytics | well inside it |
| ML workspace (`Basic`) | no charge for the workspace itself | free |

**Verify rather than trust this table.** Check Cost Management → Cost analysis
after 24–48 hours, filtered to `rg-ai300-test01`. A number that is not
approximately zero means something was provisioned that this template did not
declare.

**The template now declares compute, and billing can become hourly.** Feature
004 added a blob container, a credential-less datastore, and an **AmlCompute
cluster** (`ai300-cpu-cluster`, `Standard_DS1_v2`, dedicated, min 0 / max 2,
120 s idle before scale-down). Constitution principle I is explicit: provisioned
compute must never be left running unattended.

What that costs, measured on 2026-08-15:

| State | Charge |
| --- | --- |
| Cluster deployed, zero nodes | **nothing** — and no vCPU quota held either |
| One node allocated | 0.05774 €/node-hour, plus the 120 s idle tail |
| Two nodes for a full day (the worst case the max bounds) | ~2.77 € |

**Verify zero nodes by reading the service, not the template.** `min_instances:
0` echoed back by `az ml compute show` is the request, not the result — and that
command returned an *empty* `node_state_counts`, which is not a zero. The
positive reading comes from ARM:

```bash
az rest --method get --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-ai300-test01/providers/Microsoft.MachineLearningServices/workspaces/<ws>/computes/ai300-cpu-cluster?api-version=2026-05-01" \
  --query "properties.properties.{alloc:allocationState, current:currentNodeCount, states:nodeStateCounts}"
```

All six node-state buckets at `0` with `allocationState: Steady` is the check.
Observed scale-down after a job: ~75 seconds to `Steady` at zero, unprompted.

**Reading job logs needs the account key on this workspace.** `az ml job
download` fails with `AuthorizationPermissionMismatch`, because job logs live in
blob storage and the author's `Owner` role carries no data-plane access. Read
them directly instead:

```bash
az storage blob download --account-name <storage> --container-name azureml \
  --name "ExperimentRun/dcid.<job-name>/user_logs/std_log.txt" \
  --file ./std_log.txt --auth-mode key
```

The rates, the quota this subscription actually holds, and which compute form
to use for which exercise are measured in
[`docs/exam-notes/compute-cost-model.md`](../docs/exam-notes/compute-cost-model.md).
Three findings from it belong here, because they change how this runbook's
resource group is read:

- The subscription is **Pay-As-You-Go with the spending limit off**
  (`quotaId: PayAsYouGo_2014-09-01`), not a free trial. Nothing caps spend
  automatically; the budget alert emails, it does not stop anything.
- A **stopped compute instance still costs roughly 25 €/month** — its P10 OS
  disk and its load balancer both survive the stop. In this project a compute
  instance should be *deleted*, not stopped.
- A **managed online endpoint bills for its deployment's instances
  continuously**, whether or not any request arrives: about 42 €/month for one
  `Standard_DS1_v2`. The endpoint object itself is free; the deployment is not.

---

## 5. Deploying from continuous integration

Since feature 003 this template is also deployed by GitHub Actions, as an
identity that holds no secret. Everything below was built and verified against
this subscription; the full evidence is in
`specs/003-ci-oidc-deploy/results.md`.

### What exists, and who made it

Nothing here is created by continuous integration. It cannot create the
authority it runs with, and it is not permitted to.

| Object | Where | Created by |
| --- | --- | --- |
| Application `ai300-github-deploy` + service principal | Entra | author, `az ad` |
| Federated credential `github-azure-deploy-environment` | Entra | author, `az ad` |
| Environment `azure-deploy` + four repository secrets | GitHub | author |
| Custom role `AI300 CI Deployer (rg-ai300-test01)` + assignment | ARM | author, `infra/ci-identity.bicep` |
| Probe resource group `rg-ai300-probe` | ARM | author, `az group create` |

The application has **zero password credentials and zero certificate
credentials**, and always has. The four secrets are identifiers — which
application, which directory, which subscription, which principal — and confer
nothing without a token from the trusted issuer.

### The order matters, and getting it wrong costs an approval each time

1. Application → service principal.
2. GitHub environment `azure-deploy`: required reviewer, **`Prevent self-review`
   off**, deployment branches limited to `main`. With one author, enabling
   self-review prevention makes every deployment permanently unapprovable.
3. Store the identifiers as repository secrets.
4. **Read the subject a token actually carries** — do not construct it. Feature
   003 used a temporary `oidc-claims-probe.yml` for this and deleted it
   afterwards, because a workflow that requests a token outside the gate should
   not outlive its reason for existing. To do it again, add a workflow with
   `id-token: write` and a job carrying `environment: azure-deploy`, then:

   ```yaml
   - run: |
       set -euo pipefail
       TOKEN=$(curl -sS -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
         "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=api://AzureADTokenExchange" | jq -r '.value')
       echo "::add-mask::${TOKEN}"
       TOKEN="${TOKEN}" python3 -c 'import base64,json,os
       p=os.environ["TOKEN"].split(".")[1]; p+="="*(-len(p)%4)
       c=json.loads(base64.urlsafe_b64decode(p))
       print({k:c[k] for k in ("sub","aud","iss")})'
   ```

   Only the three claims are printed. The token itself never is.

5. Create the federated credential from that observed value.
6. `az deployment group create -g rg-ai300-test01 -f infra/ci-identity.bicep
   --parameters principalId=<service principal OBJECT id>`.

Step 6 wants the **service principal object id**, not the application (client)
id. A role assignment against a client id points at a principal that does not
exist and fails in a way that does not say so.

### Do not write the OIDC subject from documentation

This repository was created on 2026-08-05, after GitHub's immutable-subject
cutover, so its tokens carry numeric owner and repository ids:

```text
repo:Valvln@188171957/ai-mlops-genaiops@1324268843:environment:azure-deploy
```

The conventional `repo:OWNER/REPO:environment:NAME` form does **not** match here.
A mismatch surfaces as `AADSTS700213: No matching federated identity record
found for presented assertion subject '…'`, with the subject quoted back — so
read the quoted value and compare it to the credential rather than searching for
a typo in the environment name.

The subject binds to the **environment**, not to a branch. A run that has not
entered `azure-deploy` carries `…:ref:refs/heads/main` instead and cannot
exchange its token at all. The approval gate is therefore enforced by Entra, not
only by GitHub.

### ⚠️ When `main.bicep` gains a resource type, the next deployment will fail

This is the designed behaviour, not a defect, and it is the cost of a role
narrow enough to be worth having.

The CI role permits exactly the operations enumerated in
`infra/ci-identity.bicep` — each one recorded beside the failing run that
demanded it — and no more. The count is deliberately not repeated here: it grows
with every feature, and a number duplicated into prose is a number that rots.
The role carries no wildcard, no `delete`, and nothing for resource types the
template does not declare. Add a resource type and the deployment stops with:

```text
AuthorizationFailed … does not have authorization to perform action
'<the operation>' over scope '…'
```

**The fix is to add exactly the operation the error names**, to
`verifiedActions` in `infra/ci-identity.bicep`, with the failing run id recorded
as its provenance in
`specs/003-ci-oidc-deploy/contracts/role-definition.md`. Then redeploy
`ci-identity.bicep` as the author and run the workflow again.

Do not reach for a built-in role. `Contributor`, or `Role Based Access Control
Administrator`, would end the interruption and also end the property the
narrowness exists for — probe P4 would begin to succeed, and the boundary job
would go red for a good reason.

### 🚨 `main.bicep` is currently NOT DEPLOYABLE — 2026-08-17

**Read this before starting any infrastructure work.** The blocker is not in the
template's own text and will not be found by reading it.

Run `32009142428` failed the approval gate's deployment with:

```text
BadRequest: Detaching Container Registry with workspace is not supported
target: …/workspaces/ai300ml2mgou37pfmjou
```

**What happened.** Building a *custom* Azure ML environment causes Azure ML to
create a container registry and **attach it to the workspace**. Ours,
`e733615b3ab0446b9c1093c16f42a181`, was created at **06:23:21 UTC on
2026-08-17** — sixty-two seconds after the first batch endpoint invocation, by
that invocation's image build. Nobody asked for it.

`main.bicep` declares no `containerRegistry`, and feature 005's research records
that omission as deliberate: no registry was wanted, so none was declared. That
now means every redeployment of the template asks Azure to *detach* the registry
the workspace has acquired, and Azure refuses. **The failure is independent of
whatever change is being deployed** — reverting the change that happened to be in
flight does not restore deployability.

**Two things follow, and neither is optional to know:**

1. **A container registry bills at rest.** Basic tier, northeurope,
   ≈0.152 €/day ≈ **4.6 €/month**, accruing whether or not anything is built. It
   is the first charge in this project that does not stop when the compute stops
   — and it appeared on the same morning the load-balancer-at-rest question was
   settled in the other direction. § 4 of this runbook and § 7.4 of the cost
   model carry the figure.
2. **Custom environments are not free in the way curated ones are.** A curated
   environment is pulled from Microsoft's registry and attaches nothing. The
   moment a workload needs an environment built from a conda specification, the
   subscription acquires a permanent resource and the IaC drifts from reality.
   Prefer curated environments; when one will not do, expect this.

**Deciding what to do is open, and it is the author's call**, because both
directions have a cost:

| Option | Consequence |
| --- | --- |
| Declare the existing registry in `main.bicep` | Deployability returns. ≈4.6 €/month accepted indefinitely. The template carries an auto-generated name, which is a runtime value in a declarative file |
| Remove the registry | Detaching is unsupported, so the workspace would reference a deleted resource. Recreating the workspace collides with the 90-day Key Vault name lock (§ 6). **Not attempted** |
| Leave it | No new cost decision, and no infrastructure deployment is possible until it is resolved |

Until this is resolved, treat `infra/**` as frozen: a push to `main` touching it
will queue a gate whose deployment cannot succeed.

### Reading a red run correctly

| Red job | Meaning |
| --- | --- |
| `deploy` | the role is too **narrow** — an operation is missing. Ordinary. |
| `boundary` | the role is too **wide** — a probe succeeded. A real defect. |

And two traps observed during the work, both worth knowing before debugging:

- **A green run is not proof that something was deployed**, and **a red run is
  not proof that nothing was.** Run `31303842799` deployed successfully and then
  failed reading the deployment back. Check
  `az deployment group list -g rg-ai300-test01` before concluding anything.
- **An `az` command that fails may never have reached Azure.** The CLI resolves
  the subscription from a local account cache first; with no role assignment that
  cache is empty and the failure is client-side. `No subscriptions found` and
  `Subscription not found` are both this, and neither is an authorization
  refusal.

### 5.1 Reversal — undoing feature 003 completely

Twelve objects were created; twelve commands remove them. Running all of them
returns the repository and the subscription to their state before feature 003,
and leaves `main.bicep` and its resources untouched.

```bash
export PATH="/usr/local/bin:$PATH"
SP_OBJECT_ID=<service principal object id>
SUB=<subscription id>
APP_ID=<application client id>

# 1. The role assignment
az role assignment delete --assignee-object-id "$SP_OBJECT_ID" \
  --scope "/subscriptions/$SUB/resourceGroups/rg-ai300-test01"

# 2. The custom role definition
az role definition delete --name "AI300 CI Deployer (rg-ai300-test01)"

# 3. The federated credential
az ad app federated-credential delete --id "$APP_ID" \
  --federated-credential-id github-azure-deploy-environment

# 4. The service principal
az ad sp delete --id "$APP_ID"

# 5. The application registration
az ad app delete --id "$APP_ID"

# 6. The probe resource group
az group delete --name rg-ai300-probe --yes --no-wait

# 7-10. The four repository secrets
gh secret delete AZURE_CLIENT_ID        -R Valvln/ai-mlops-genaiops
gh secret delete AZURE_TENANT_ID        -R Valvln/ai-mlops-genaiops
gh secret delete AZURE_SUBSCRIPTION_ID  -R Valvln/ai-mlops-genaiops
gh secret delete AZURE_CLIENT_OBJECT_ID -R Valvln/ai-mlops-genaiops

# 11. The GitHub environment, and with it the approval gate
gh api --method DELETE repos/Valvln/ai-mlops-genaiops/environments/azure-deploy

# 12. The deploying workflow
git rm .github/workflows/infra-deploy.yml
```

Deleting the role assignment (1) alone is enough to stop CI deploying, and is
the right first move if something is wrong and the cause is not yet known. It is
reversible by redeploying `ci-identity.bicep`.

Steps 4 and 5 are **not** reversible: a new application gets a new client id, so
the secrets and the federated credential would have to be recreated. Nothing is
soft-deleted and no name is held — unlike the Key Vault, this feature walks
through no one-way doors.

`infra/ci-identity.bicep` may be left in place after a reversal. It deploys
nothing on its own and documents what the authority was.

---

## 6. Teardown

Deleting the resource group removes the billable surface in one command:

```bash
az group delete --name rg-ai300-test01 --yes --no-wait
```

**But re-read the one-way doors first.** After this runs:

- The Key Vault is soft-deleted with purge protection, holding
  `ai300kv2mgou37pfmjou` for 90 days. Recreating `rg-ai300-test01` will collide;
  use `rg-ai300-test02`.
- The ML workspace name is likewise held for its retention window.

```bash
# Inspect what is being held after a teardown
az keyvault list-deleted \
  --query "[].{name:name, purgeDate:properties.scheduledPurgeDate}" -o table
```

**Portal equivalent**: Resource group → Delete resource group → type the name to
confirm. Soft-deleted vaults are visible under Key Vaults → Manage deleted
vaults.

---

## Summary checklist

- [x] Five resource providers report `Registered`
- [x] Target region confirmed eligible (`westeurope` is not)
- [x] Resource group created, name chosen with the 90-day trap in mind
- [x] `az bicep build` exits 0 with no output
- [x] `what-if` shows 5 creates, no container registry, no compute
- [x] `managedNetwork` declared explicitly rather than inherited
- [x] Deployment succeeded
- [x] `az resource list` returns the resources the baseline recorded — **6**, not
      the 5 originally written here; see section 3
- [ ] Cost analysis checked after 24–48 hours
- [x] Teardown plan decided before walking away
- [x] Workspace identity permissions understood — and found **not** to be the
      author's to reduce while the identity is system-assigned; see "Workspace
      identity permissions" above
- [x] System data stores switched from account keys to the workspace identity
- [ ] Whether a user-assigned identity escapes the platform's automatic grants —
      **untested hypothesis**, not a finding
- [x] Continuous integration deploys this template with no stored secret, as an
      identity scoped to one resource group — see section 5
- [x] That identity's authority proven bounded by four refused actions, asserted
      on every run rather than captured once
- [x] That identity's grant proven load-bearing: 403 without it, 201 with it,
      same request
- [x] Reversal for feature 003 written as twelve runnable commands — section 5.1
