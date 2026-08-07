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

**The check that matters most**: `az resource list` must return **5** rows. If a
container registry appears, the workspace provisioned one despite the template —
investigate before doing anything else, because that is a recurring charge.

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

**The real cost risk is not here — it is next.** This template declares no
compute. The moment a compute instance or cluster is added, billing becomes
hourly and continues whether or not anything is running on it. Constitution
principle I is explicit: provisioned compute must never be left running
unattended.

---

## 5. Teardown

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
- [x] `az resource list` returns exactly 5 resources
- [ ] Cost analysis checked after 24–48 hours
- [x] Teardown plan decided before walking away
