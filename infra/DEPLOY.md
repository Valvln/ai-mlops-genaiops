# Deploying `main.bicep` — runbook

This is the first time anything in this repository is deployed to Azure. Every
step before now was local and free. From here on, resources are real and the
free-trial credit is being spent.

Read the "One-way doors" section before running anything. Two of the choices
already baked into the template cannot be undone for 90 days.

**Subscription**: Azure subscription 1 (`5900fbc9-a139-49ed-9987-ba560c147eb7`)
**Signed in as**: ValerioQuaranta@Valvln.onmicrosoft.com
**Template region default**: `westeurope`

---

## 0. Pre-flight (do this first — it is not optional)

### 0.1 Register the resource providers

All five providers this template needs are currently **NotRegistered** on this
subscription. A deployment against an unregistered provider fails immediately
with `MissingSubscriptionRegistration`.

```bash
export PATH="/usr/local/bin:$PATH"

for ns in Microsoft.Storage Microsoft.KeyVault Microsoft.OperationalInsights \
          Microsoft.Insights Microsoft.MachineLearningServices; do
  az provider register --namespace "$ns"
done
```

Registration is free and asynchronous — it takes a few minutes per provider.
Wait until all five report `Registered`:

```bash
for ns in Microsoft.Storage Microsoft.KeyVault Microsoft.OperationalInsights \
          Microsoft.Insights Microsoft.MachineLearningServices; do
  printf "%-38s %s\n" "$ns" \
    "$(az provider show --namespace "$ns" --query registrationState -o tsv)"
done
```

**Portal equivalent**: Subscriptions → *Azure subscription 1* → Settings →
Resource providers → search each namespace → Register.

### 0.2 Create the resource group

The subscription currently has no resource groups. Pick the name deliberately —
see the 90-day trap below, because this name is an input to every generated
resource name.

```bash
az group create --name rg-ai300-learning --location westeurope
```

**Portal equivalent**: Resource groups → Create → Subscription *Azure
subscription 1*, Name `rg-ai300-learning`, Region *West Europe* → Review +
create.

### 0.3 Rebuild and confirm the template still compiles

```bash
az bicep build --file infra/main.bicep
```

Expect exit 0 and **no output**. Anything printed here is a finding — stop and
resolve it before deploying.

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

**Consequence**: tear down `rg-ai300-learning` today and redeploy to
`rg-ai300-learning` next week, and the deployment fails on the Key Vault. You
would have to wait out the 90 days or choose a different resource group name.

**Mitigations**, pick one before deploying:

- Accept it and commit to keeping this resource group name for the duration.
- Use a throwaway resource group name for the first deployment (for example
  `rg-ai300-test01`) so a redeploy can move to `-test02` without waiting.

### Machine learning workspace soft-delete

Azure ML workspaces are also subject to soft-delete, with the workspace name
held for a retention period after deletion. Confirm the current behaviour and
retention window for this subscription before relying on being able to reuse
`ai300ml<hash>` immediately after a teardown. Treat workspace names the same way
as vault names: assume reuse is blocked for a while.

### Provider registration

Registering a provider is effectively permanent for the subscription. It is
harmless and free — noted only for completeness.

---

## 1. Dry run — `what-if`

Never run the deployment before this. `what-if` resolves every expression and
shows exactly what Azure will create, without creating anything.

```bash
az deployment group what-if \
  --resource-group rg-ai300-learning \
  --template-file infra/main.bicep
```

**What to check in the output**:

| Check | Expected |
| --- | --- |
| Number of resources to `+ Create` | exactly 5 |
| Container registry | absent from the whole output |
| Any compute resource | absent |
| ML workspace `sku` | `Basic` |
| ML workspace `identity.type` | `SystemAssigned` |
| `managedNetwork` on the workspace | inspect it — see the note below |

**On `managedNetwork`**: the template leaves this property unset, so the service
default applies, and this dry run is the first time that default is visible.
Managed network isolation can provision billable infrastructure. If `what-if`
shows an isolation mode other than disabled, stop and decide deliberately before
deploying.

**Portal equivalent**: there is no true `what-if` in the portal deployment
blade. It validates the template and shows a Review page, which is weaker. Run
`what-if` from the CLI even if you intend to deploy from the portal.

---

## 2. Deploy

```bash
az deployment group create \
  --resource-group rg-ai300-learning \
  --template-file infra/main.bicep \
  --name ai300-ml-workspace-001
```

Naming the deployment (`--name`) makes it addressable afterwards; without it you
get a timestamped name that is awkward to reference.

Expect this to take several minutes — the ML workspace is the slow part.

### Portal equivalent

The portal deploys ARM JSON, not Bicep, so it consumes the compiled
`infra/main.json` — produced by `az bicep build`, gitignored but present
locally.

1. Portal → search **Deploy a custom template**
2. **Build your own template in the editor**
3. **Load file** → select `infra/main.json`
4. **Save**
5. Subscription *Azure subscription 1*, Resource group `rg-ai300-learning`
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
  --resource-group rg-ai300-learning \
  --name ai300-ml-workspace-001 \
  --query "{state:properties.provisioningState, outputs:properties.outputs}"

# Exactly 5 resources, and nothing unexpected alongside them
az resource list --resource-group rg-ai300-learning \
  --query "[].{name:name, type:type}" -o table

# The managed identity now has a real principal id — this is what future role
# assignments attach to
az ml workspace show --resource-group rg-ai300-learning \
  --name "$(az deployment group show -g rg-ai300-learning \
             -n ai300-ml-workspace-001 \
             --query properties.outputs.workspaceName.value -o tsv)" \
  --query identity 2>/dev/null \
  || echo "az ml extension not installed - use the portal or 'az resource show'"
```

**The check that matters most**: `az resource list` must return **5** rows. If a
container registry appears, the workspace provisioned one despite the template —
investigate before doing anything else, because that is a recurring charge.

**Portal equivalent**: Resource group `rg-ai300-learning` → Overview lists the
resources; Settings → Deployments → `ai300-ml-workspace-001` → Outputs shows the
four output values.

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
after 24–48 hours, filtered to `rg-ai300-learning`. A number that is not
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
az group delete --name rg-ai300-learning --yes --no-wait
```

**But re-read the one-way doors first.** After this runs:

- The Key Vault is soft-deleted with purge protection, holding its name for 90
  days. Recreating a resource group with the same name will collide.
- The ML workspace name is likewise held for its retention window.

```bash
# Inspect what is being held after a teardown
az keyvault list-deleted --query "[].{name:name, purgeDate:properties.scheduledPurgeDate}" -o table
```

**Portal equivalent**: Resource group → Delete resource group → type the name to
confirm. Soft-deleted vaults are visible under Key Vaults → Manage deleted
vaults.

---

## Summary checklist

- [ ] Five resource providers report `Registered`
- [ ] Resource group created, name chosen with the 90-day trap in mind
- [ ] `az bicep build` exits 0 with no output
- [ ] `what-if` shows 5 creates, no container registry, no compute
- [ ] `managedNetwork` default inspected and accepted
- [ ] Deployment succeeded
- [ ] `az resource list` returns exactly 5 resources
- [ ] Cost analysis checked after 24–48 hours
- [ ] Teardown plan decided before walking away
