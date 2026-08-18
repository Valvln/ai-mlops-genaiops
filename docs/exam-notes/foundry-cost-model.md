# The Azure AI Foundry cost model — priced before anything is deployed

Block 3 covers Foundry. This note prices it **before** a resource exists, because
the mechanism that already cost this project once — a platform provisioning a
billed dependency nobody asked for — is exactly the mechanism a Foundry hub
implements by design.

**Priced on**: 2026-08-18
**Currency**: EUR, requested explicitly from the retail prices API
**Regions checked**: `northeurope` (this project's region) and `swedencentral`
**Nothing in this note was deployed.** Every figure is from a public price list,
a read-only availability query, or Microsoft documentation cited inline.

---

## 0. How to reproduce every figure here

**Public retail prices** — no authentication, no subscription touched:

```bash
# All Foundry model meters for a region, in EUR. `Foundry Models` is the
# serviceName; `Azure OpenAI` is a productName underneath it. Filtering on
# serviceName eq 'Azure OpenAI' returns zero rows and looks like an outage.
curl -s "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode='EUR'&\$filter=serviceName%20eq%20'Foundry%20Models'%20and%20armRegionName%20eq%20'northeurope'" \
  | python3 -m json.tool
```

**What can actually be deployed** — read-only, and it needs no existing account:

```bash
export PATH="/usr/local/bin:$PATH"

# Which models exist in a region, and under which deployment SKUs. This is the
# query that decides the block, not the price list - see section 4.
az cognitiveservices model list -l northeurope \
  --query "[?kind=='OpenAI'].{name:model.name, skus:join(',',model.skus[].name)}" -o tsv
```

**Unit trap.** Meter names carry their own unit. The `Azure OpenAI` product
prices per **1K** tokens; the `Azure OpenAI GPT5` product prices per **1M**.
Comparing the two raw numbers understates the older models by 1000×. Normalise
to 1M before comparing anything.

---

## 1. What each Foundry path creates

There are two, and they are not variants of one thing. This is the single most
cost-relevant fact in the block.

### 1a. Foundry resource + Foundry project — the lean path

| Resource | ARM type | Required | Bills at rest? |
| --- | --- | --- | --- |
| Microsoft Foundry | `Microsoft.CognitiveServices/accounts`, kind `AIServices` | yes | **no** — usage only |
| Foundry project | `Microsoft.CognitiveServices/accounts/projects` | yes | **no** — subresource |

That is the whole list. **No storage account, no key vault, no container
registry, no Application Insights.** A Foundry project is a child resource of the
account, and the account is billed for the services consumed through it, not for
existing ([Plan and manage costs][mc], [Choose an Azure resource type][rt]).

### 1b. Hub + hub-based project — the path that carries dependencies

A hub is `Microsoft.MachineLearningServices/workspaces` with `kind: hub`. It is,
in Microsoft's own words, "an implementation of Azure Machine Learning and
requires multiple Azure services as dependencies" ([Hubs and hub-based project
overview][hub]). **If you do not supply them, they are created for you.**

| Dependency | ARM type | Optional? | Bills at rest? | Rate |
| --- | --- | --- | --- | --- |
| Microsoft Foundry | `Microsoft.CognitiveServices/accounts` | no | no | usage only |
| Storage account | `Microsoft.Storage/storageAccounts` | no | effectively no | 0.122 € over this project's first 18 days, nearly all write operations during jobs |
| Key Vault | `Microsoft.KeyVault/vaults` | no | effectively no | 0.000253 € over the same 18 days |
| **Container registry** | `Microsoft.ContainerRegistry/registries` | yes | **YES** | **0.1462 €/day = 4.4 €/month**, Basic, forever |
| App Insights + Log Analytics | `Microsoft.Insights/components`, `Microsoft.OperationalInsights/workspaces` | yes | per GB ingested | no billed row in this project to date |
| **Azure AI Search** | `Microsoft.Search/searchServices` | yes | **YES, unless Free** | Free **0.00 €/h**; Basic **0.08864 €/h = 2.13 €/day = 63.8 €/30 days** |

Two entries in that table are the whole risk:

- **The registry.** Its stated purpose on a hub is to store "docker images
  created when using custom runtime for prompt flow" — the same class of event
  that acquired one on 2026-08-17, and at the same rate. See
  `compute-cost-model.md` § 7.4.
- **AI Search.** A Basic search service costs **fourteen times a day** what the
  registry does, and it does not stop either. The Free tier is genuinely 0.00 €/h
  on the price list, so the tier choice is the entire decision.

**Neither the container registry nor Application Insights can be detached once
attached** ([How to create and manage a hub][create]). This is the same one-way
door already recorded for the ML workspace: the template stops being able to
describe the resource it created.

---

## 2. The only question that matters: does it stop?

Ordered by that criterion rather than by price, which is how this project's two
expensive surprises would both have been caught in advance.

| Item | Rate | Stops when? |
| --- | --- | --- |
| Foundry resource, Foundry project | — | nothing to stop; no standing charge |
| Model deployment, **Standard** (per token) | see § 3 | **on its own** — no calls, no charge |
| Storage, Key Vault | fractions of a cent/day | with the resource group |
| **Container registry (Basic)** | 0.1462 €/day | **only when deleted** |
| **AI Search (Basic)** | 2.13 €/day | **only when deleted** |
| **Model deployment, Provisioned (PTU)** | § 3 — from 315.93 €/day | **only when deleted.** "Provisioned deployments can't be paused. Billing stops only when the deployment is deleted" ([PTU billing][ptub]) |
| **Fine-tuned model hosting** | **1.4919 €/h = 35.81 €/day** | **only when deleted**; charged "even if the model is unused" ([Plan and manage costs][mc]) |
| Managed compute (open-source models on dedicated VMs) | A100 80GB **3.4664 €/h**; H100 80GB **6.9416 €/h** | only when deleted |

The last three lines are the block's real hazards. The fine-tuned hosting rate is
block 5 material and is recorded here because it is the same meter family.

---

## 3. Per-token versus provisioned throughput

### 3a. The two billing forms

| | **Standard** (per token) | **Provisioned** (PTU) |
| --- | --- | --- |
| Billed on | tokens actually consumed | **PTUs deployed, regardless of traffic** |
| Meter starts | on the request | when the deployment is created |
| Meter stops | when the request ends | **when the deployment is deleted** |
| Can it be paused? | not applicable | **no** |
| Minimum spend | zero | see § 3b |
| SLA | none | latency target per model |

Microsoft's own guidance points the same way for this use case: "Standard
deployments remain the better fit for development, testing, low-volume usage"
([Provisioned throughput][ptu]).

### 3b. What a provisioned deployment costs at its floor

Every current Azure OpenAI model has a **minimum deployment of 15 PTU** for
Global and Data Zone Provisioned, in increments of 5; Regional Provisioned
minimums are 25 or 50 PTU ([PTU sizing][sizing]). So the floor is not a
theoretical 1 PTU:

| Deployment type | €/PTU/hour | Minimum | Floor per hour | Floor per day | Floor per 30 days |
| --- | --- | --- | --- | --- | --- |
| Global Provisioned | 0.877578 | 15 PTU | **13.16 €** | **315.93 €** | **9 478 €** |
| Data Zone Provisioned | 0.965336 | 15 PTU | 14.48 € | 347.52 € | 10 426 € |
| Regional Provisioned | 2.106187 | 25 PTU | 52.65 € | 1 264 € | 37 912 € |

Reservations discount the rate in exchange for a term commitment — Global
Provisioned is **228.17025 € per PTU for one month**, **2 327.34 € per PTU for one
year** — so the cheapest possible reserved commitment is 15 × 228.17 =
**3 422.55 € for one month.**

### 3c. The comparison, in one line

The entire modelling budget for this block, generously sized at 10M input and 2M
output tokens on the cheapest deployable model, is **1.14 €** (§ 4). **One hour**
of the smallest possible provisioned deployment costs **11.5 times** that, and it
cannot be paused.

**Per-token is the only acceptable form here, and it is not close.** Provisioned
throughput is exam material to *recognise* and to *size*, and the sizing formula
in [PTU sizing][sizing] can be exercised on paper for free. It is not something to
deploy.

---

## 4. The cheapest usable model — and why the region decides it

**The price list is not an availability list.** Every meter below is priced
identically in `northeurope` and `swedencentral` (verified, both regions, same
retail figures to six decimals). What differs is which deployment SKUs a region
will actually accept — and in `northeurope` most of the cheap models are offered
**only as `GlobalProvisionedManaged`**, which is PTU.

`az cognitiveservices model list`, run against both regions:

| Model | Deployable in `northeurope` as | Deployable in `swedencentral` as |
| --- | --- | --- |
| `gpt-5.4-nano` | **GlobalStandard**, DataZoneStandard | GlobalStandard |
| `gpt-5.4-mini` | **GlobalStandard**, GlobalProvisionedManaged | GlobalStandard, DataZoneStandard, PTU, GlobalBatch |
| `gpt-5-nano` | **absent** | **GlobalStandard**, DataZoneStandard |
| `gpt-4.1-nano` | **PTU only** | GlobalStandard, DataZoneStandard, DeveloperTier, PTU, **GlobalBatch** |
| `gpt-4o-mini` | **PTU only** | GlobalStandard, PTU, GlobalBatch |
| `text-embedding-3-small` | GlobalStandard | GlobalStandard, DataZoneStandard |

Prices, normalised to EUR per 1M tokens, Global meters:

| Model | Input | Cached input | Output | Batch in / out |
| --- | --- | --- | --- | --- |
| `gpt-5-nano` | **0.04388** | 0.00439 | **0.35103** | — |
| `gpt-4.1-nano` | 0.08800 | 0.02200 | 0.35100 | 0.04400 / 0.17600 |
| `gpt-5.4-nano` | 0.17552 | 0.01755 | 1.09697 | — |
| `gpt-5.4-mini` | 0.65818 | 0.06582 | 3.94910 | — |
| `text-embedding-3-small` | 0.01800 | — | — | — |
| `text-embedding-3-large` | 0.11396 | — | — | — |

**Two defensible choices, and they are a genuine trade-off:**

- **Stay in `northeurope`** and use **`gpt-5.4-nano`**. It is the cheapest model
  the project's pinned region will deploy per token. 10M in + 2M output =
  1.76 + 2.19 = **3.95 €**.
- **Add `swedencentral` for block 3 only** and use **`gpt-5-nano`**, four times
  cheaper on input and identical on output: 10M in + 2M out =
  0.44 + 0.70 = **1.14 €**. It also unlocks the **Batch** SKU on `gpt-4.1-nano`
  at half the standard rate, which is itself a Domain 3 topic.

Both are rounding errors against the registry's 4.4 €/month. The reason to prefer
the second is not the money — it is that `northeurope` cannot demonstrate three
deployment types the exam asks about (Batch, DeveloperTier, DataZoneStandard on a
nano model), and an exercise that cannot be run is a gap.

`westeurope` remains unavailable to this subscription for the reason recorded in
`infra/DEPLOY.md` § 0.2, which is unrelated to any of this.

---

## 5. Local at zero cost, versus requires Azure

| Topic (Domain 3) | Local, free | Requires Azure | Note |
| --- | --- | --- | --- |
| Prompt versioning with Git | ✅ entirely | — | Prompts as files, diffs, tags. Nothing about this is Azure-specific |
| Prompt design, variants, side-by-side comparison | ✅ structure and harness | inference calls only | The comparison harness is local; only the completions cost tokens |
| Model selection for a use case | ✅ entirely | — | `az cognitiveservices model list` is read-only and free; the price list is public. § 4 of this note *is* the exercise |
| PTU sizing arithmetic | ✅ entirely | — | The formula and per-model tables are published; sizing is paper work ([PTU sizing][sizing]) |
| IaC for Foundry (Bicep) | ✅ authoring + `az bicep build` | deployment | Same split as blocks 1–2: compiling is free, `what-if` needs a subscription and is still free |
| RBAC / managed identity for Foundry | ✅ reading role definitions | assignment | Role definition JSON can be written and reviewed offline |
| Deploying a foundation model | — | ✅ | The one thing with no local substitute |
| Versioning and production deployment of a model | — | ✅ | Deployment names and model versions are server-side objects |
| Network security / private endpoints | ✅ theory | ✅ to build | Already closed as declared theory in block 1 for the same cost reason |
| Content filters | ✅ configuration reading | ✅ to attach | On Azure OpenAI Standard deployments the default filter is **included in token pricing**, not billed separately ([Default guardrail policies][safety]). Serverless API deployments of non-Azure models can be billed separately under Content Safety |

**Content Safety, standalone.** No pay-as-you-go transaction meter is published
for `northeurope`; only commitment tiers appear, from **281.70 €/month** for 1M
text transactions. Nothing in this block should ever reach that meter, and if it
appears on a bill it means a serverless non-Azure model deployment was created.

---

## 6. What this note recommends

Stated as a recommendation because the decision is the author's.

1. **Use a Foundry resource with Foundry projects. Do not create a hub.** § 1
   shows the hub path re-creates the exact dependency chain that has already cost
   this project money, including a registry that cannot be detached. The hub is
   needed for open-source model hosting and fine-tuning — block 5 questions —
   and those are already scheduled as theory.
2. **Standard (per-token) deployments only.** § 3.
3. **AI Search: Free tier or nothing.** The Basic tier costs more per day than
   everything else in the block combined.
4. **Nothing that bills at rest gets created without being written down first**,
   with its daily rate and its deletion command, the way § 2 lists them.

Under these constraints the projected running cost of block 3 is **the tokens
plus zero standing charge** — a few euro in total, and nothing at all while the
environment is destroyed.

---

## Sources

- [Hubs and hub-based project overview][hub] — the dependency table in § 1b
- [Choose an Azure resource type for Foundry][rt] — Foundry resource vs hub
- [How to create and manage a Foundry hub][create] — ACR and App Insights cannot be disassociated
- [Plan and manage costs for Foundry][mc] — no charge for the resource itself; fine-tuned hosting billed while deployed
- [Provisioned throughput for Foundry Models][ptu] — deployment categories, minimums, meter start/stop
- [Provisioned throughput billing and cost management][ptub] — "can't be paused"; reservations
- [Determine PTU sizing for a workload][sizing] — per-model minimum deployment and increments
- [Default guardrail policies for Azure OpenAI][safety] — content filtering included in token pricing
- [Azure Retail Prices API][prices] — every euro figure in this note

[hub]: https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/ai-resources?view=foundry-classic
[rt]: https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/resource-types
[create]: https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/create-azure-ai-resource?view=foundry-classic
[mc]: https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs
[ptu]: https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/provisioned-throughput
[ptub]: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/provisioned-throughput-onboarding
[sizing]: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/provisioned-throughput-sizing
[safety]: https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/default-safety-policies
[prices]: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
