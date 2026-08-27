# Cost model for block 5 — RAG and fine-tuning

**Status: list prices, read from the Azure Retail Prices API on 2026-08-27.
Nothing here is measured yet.** Every figure is EUR, `northeurope` unless stated.
The same distinction that `compute-cost-model.md` § 7.5 and `foundry-cost-model.md`
insist on applies: **a list price is a prediction, and an absent line in Cost
Management is not a confirmed zero.**

This note exists so the block 5 spec can name a daily rate and a deletion command
next to every resource, as the cost constraint requires.

---

## 1. Azure AI Search — the tier decision, priced

The query behind the table (public, unauthenticated, free, and repeatable):

```bash
curl -s "https://prices.azure.com/api/retail/prices?currencyCode='EUR'&\$filter=serviceName%20eq%20'Azure%20Cognitive%20Search'%20and%20armRegionName%20eq%20'northeurope'" \
  | python3 -m json.tool
```

⚠️ **`serviceName` is still `Azure Cognitive Search`.** The product was renamed to
Azure AI Search; the billing meter was not. Filtering on the current product name
returns nothing, which reads exactly like "this service has no meters".

| Tier | €/hour | **€/day** | €/30 days |
| --- | ---: | ---: | ---: |
| **Free** (`Free Unit`) | **0,0000** | **0,00** | **0,00** |
| Basic (`Basic Unit`) | 0,0887 | **2,1288** | 63,86 |
| Standard S1 | 0,2952 | 7,08 | 212,6 |
| Standard S2 | 1,1809 | 28,34 | 850,2 |
| Standard S3 | 2,3617 | 56,68 | 1.700,4 |
| Storage Optimized L1 | 3,3730 | 80,95 | 2.428,6 |
| Storage Optimized L2 | 6,7452 | 161,88 | 4.856,5 |

**Basic is 2,13 €/day and it does not stop.** It is billed per search unit per
hour from creation to deletion, with no idle state and no scale-to-zero — the
same failure mode as the container registry that cost this project 4,4 €/month
while nobody was looking (`compute-cost-model.md`). Over the eight days this
block has, Basic is **17 €**; over the two-week absence that follows, another
**30 €** with nobody present to notice.

**Decision: Free tier or nothing.** What that buys and what it forbids is in
`rag-vector-store-and-indexing.md` § 5. The constraint is not a compromise here —
the Free tier supports vector search, hybrid search **and semantic ranking**, so
it covers everything the domain asks about except scale.

### Semantic ranker meters

| Meter | Rate | Applies |
| --- | ---: | --- |
| `Free queries` | **0,0000 €/1K** | free plan, **all tiers** |
| `Semantic Ranker queries` | 0,8786 €/1K | standard plan, Basic+ |
| `Semantic Ranker Overage Queries` | 1,7572 €/1K | beyond the standard plan |
| `Semantic Ranker Unit` | 14,1633 €/**day** | — |

A Free-tier service **cannot** be switched to the standard plan — Learn: «Standard…
requires the Basic tier or higher». So on Free, semantic ranking is billed at the
first row and exhausting the allowance «returns a billing error», not a charge.
Details in `rag-hybrid-search-and-ranking.md` § 5.

### Other Search meters worth knowing exist

`Document Cracking Image Extraction` (0,5711–0,8786 €/1K) and
`Custom Entity Skills Text Records` (0,2197–0,8786 €/1K) bill **enrichment
transactions, not the service**. They are avoided by not putting image extraction
or custom-entity skills in a skillset. On Free the enrichment cap is 20
transactions per indexer per day anyway.

---

## 2. What Search does *not* charge for

> «Vector search is available in all regions and on all tiers **at no extra
> charge**. However, generating embeddings or using AI enrichment for
> vectorization might incur charges from the model provider.»

So there is no vector meter, no per-query meter for BM25 or vector search, and no
storage meter separate from the tier. **On the Free tier, the entire retrieval
side of this block is 0,00 €.** The spend is upstream — in the embedding calls —
and it is token-priced, which means it is bounded by attention rather than by
time. That is the *variable* class in the tracker's cost taxonomy, the one this
project has repeatedly found harmless.

---

## 3. Embeddings and chat tokens

| Model | Deployment | Rate |
| --- | --- | ---: |
| `text-embedding-3-large` | global | 0,0001 €/1K |
| `text-embedding-3-large` | regional (northeurope) | 0,0002 €/1K |
| `text-embedding-3-large` | regional (swedencentral) | 0,0001 €/1K |
| `text-embedding-3-small` | global / regional | ⚠️ **0,0 exactly** |
| `gpt-4.1-mini` input | GlobalStandard | 0,0004 €/1K |
| `gpt-4.1-mini` output | GlobalStandard | 0,0014 €/1K |
| `gpt-4.1-mini` cached input | GlobalStandard | 0,0001 €/1K |
| `gpt-4.1-mini` input / output | regional | 0,0005 / 0,0019 €/1K |

⚠️ **The `text-embedding-3-small` rate is published as literal `0.0`** in EUR, in
both regions and for both deployment types. That is a publication artifact of the
price list, not a free model — the same API publishes `text-embedding-3-large` at
0,0001 €/1K, and small is cheaper than large but not free. **Treat it as "below
the published precision", and do not build an argument on a zero that came from
rounding.** This repository has already been caught once treating an absent line
as a measured zero (`foundry-cost-model.md`, the resting-cost prediction), and
the correction is the same: verify in Cost Management, or say "unknown".

### What a corpus costs to embed

With `text-embedding-3-large` at 0,0002 €/1K regional, a corpus of **1 million
tokens** costs **0,20 €** to embed once. Re-chunking re-embeds it. A sweep across
four chunk sizes is 0,80 €.

That is the entire budget of the interesting part of this block, and it is why
the chunk-size axis is affordable at all — see `rag-chunking-strategies.md` § 7.
Compare against block 3's whole build: ~1.300 tokens.

---

## 4. Fine-tuning — the numbers that end the discussion

| Meter | Rate | Per day |
| --- | ---: | ---: |
| `gpt-4.1-mini FT Training regional` | 0,0058 €/1K | one-off |
| `gpt-4.1-mini FT Training global` | 0,0044 €/1K | one-off |
| `gpt-4.1-mini FT Training` (swedencentral, regional) | 0,0053 €/1K | one-off |
| **`gpt-4.1-{nano,mini}-ft hosting`, any region** | **1,4937 €/hour** | **35,85 €/day** |
| `gpt-4.1-mini-ft input / output` global | 0,0004 / 0,0014 €/1K | = base model |

Two readings, both in `fine-tuning-vs-rag.md` § 3:

- **Training is affordable**: one million training tokens is 4,40–5,80 €.
- **Hosting is not**: 35,85 €/day, flat across model sizes, from deployment until
  someone deletes it, on a subscription whose spending limit is Off.

**Block 5 does not fine-tune.** Same verdict, same reasoning and the same shape as
provisioned throughput in block 3 — 15 units minimum at 13,16 €/hour, stopped
only by deleting the deployment.

For reference, if it were ever run, the two rates make the break-even explicit:
one day of hosting equals about **25 million output tokens** on the base model.
This project's entire August was ≈0,81 €.

---

## 5. Teardown — the commands, next to the rates

The constitution's cost principle and this project's «the environment is
disposable» rule both require that nothing billing at rest gets created without
its deletion command written down first. For block 5 that list is short:

```bash
export PATH="/usr/local/bin:$PATH"

# 1. What exists, before deciding anything
az resource list -g rg-ai300-rag --query "[].{name:name,type:type}" -o table

# 2. The search service, if one was created outside the resource group
az search service delete -n <service> -g <rg> --yes

# 3. Everything, which is the supported path
az group delete -n rg-ai300-rag --yes --no-wait

# 4. A fine-tuned deployment, IF one is ever created — 1,4937 €/hour until this runs
az cognitiveservices account deployment delete \
  -n <account> -g <rg> --deployment-name <deployment>

# 5. Confirm, do not assume
az group exists -n rg-ai300-rag
```

⚠️ Two traps this repository has already paid for, both still live:

- **The Key Vault name is held for 90 days** after a teardown when purge
  protection is on, and resource names derive from
  `uniqueString(resourceGroup().id)`. `infra/DEPLOY.md` has the detail. Block 5's
  resource group should not collide with a name that has been used before.
- **A Foundry account name is soft-deleted for 48 hours.** The tracker records
  `ai300fdrylkcq74thutjeq` in `rg-ai300-foundry` and the deliberate decision not
  to purge it. If block 5 redeploys `foundry.bicep` into a group with the same
  name before that window has expired, the deployment collides.

And one specific to Search, from the limits article: *«A free search service might
be deleted after extended periods of inactivity.»* Convenient, but **not a
teardown mechanism** — it is not scheduled, not announced, and not a substitute
for the template being able to rebuild what it describes.

---

## 6. Verifying, rather than predicting

Everything above is a list price. The commands that turn it into a measurement:

```bash
# What the service thinks it may hold (data plane, free)
GET https://{service}.search.windows.net/servicestats?api-version=2026-04-01

# What was actually billed — Cost Management, NOT `az consumption usage list`,
# which returns records with cost: None on this subscription
az costmanagement query --type ActualCost --timeframe Custom \
  --time-period from=<start> to=<end> \
  --scope "/subscriptions/<sub>" --dataset-aggregation '{...}'
```

The discipline that `foundry-cost-model.md` established and this note inherits:
**compare two time windows, and keep a control.** A resource group that produces
no line on a day when other groups do is a measured zero. A resource group that
produces no line on a day when nothing produced a line is an absent dataset.
That distinction is what made block 3's resting-cost measurement (T027) readable
and what its predecessor lacked.

**A success criterion on cost should therefore read as a comparison, not as a
number** — for example: on a full day with the search service in place and no
queries, the block 5 resource group contributes no cost line while at least one
other group in the same subscription does.

---

## Sources

- Azure Retail Prices API — `serviceName eq 'Azure Cognitive Search'`, northeurope, EUR — read 2026-08-27; §§ 1, 2
- Azure Retail Prices API — `contains(meterName,'text-embedding')` and `contains(meterName,'4.1 mini')`, northeurope + swedencentral, EUR — read 2026-08-27; §§ 3, 4
- Azure Retail Prices API — `contains(meterName,'hosting')`, northeurope + swedencentral, EUR — read 2026-08-27; § 4
- [Vector search overview](https://learn.microsoft.com/en-us/azure/search/vector-search-overview) — read 2026-08-27; § 2, the no-extra-charge statement
- [Service limits for tiers and SKUs](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity) — read 2026-08-27; § 5, inactivity deletion
- [Enable or disable semantic ranker billing](https://learn.microsoft.com/en-us/azure/search/semantic-how-to-enable-disable) — read 2026-08-27; § 1
- `compute-cost-model.md`, `foundry-cost-model.md` — the measurement discipline in § 6
- `infra/DEPLOY.md` — the Key Vault and soft-delete traps in § 5
- `fine-tuning-vs-rag.md` § 3 — what § 4 decides
