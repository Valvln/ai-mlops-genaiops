# Contract — the free search service, the index, and what the tier really permits

Covers **User Story 2**, FR-003 to FR-007, SC-005 and SC-006.

---

## 1. `infra/search.bicep` — a new template

Separate from `foundry.bicep` on purpose: different lifecycle, and mixing a new
resource type into that file would make "the second deployment still works" an
ambiguous claim.

```text
resource searchService 'Microsoft.Search/searchServices@2025-05-01'
```

| Property | Value | Why |
| --- | --- | --- |
| `sku.name` | **`free`** | FR-005. Basic is 2,13 €/day and does not stop |
| `location` | `swedencentral` | [R2](../research.md): semantic ranker **on the free tier**, and `northeurope` cannot create new services at all |
| `replicaCount` / `partitionCount` | 1 / 1 | the only values the tier accepts |
| `hostingMode` | `default` | `highDensity` is standard3-only |
| `semanticSearch` | **`free`** | FR-006. `standard` requires Basic+ and would bill |
| `disableLocalAuth` | **`true`** | keyless, matching the Foundry account |
| `authOptions` | ⚠️ **omitted entirely** | it *cannot be set* when `disableLocalAuth` is true. Setting both is a template that will not deploy |
| `publicNetworkAccess` | `Enabled` | no private endpoint; out of scope and it would bill |

**Two role assignments to the caller**, at the service scope, by GUID:

| Role | GUID | Needed for |
| --- | --- | --- |
| Search Service Contributor | `7ca78c08-252a-4471-8644-bb5ff32d4ba0` | create the index; **read `/servicestats`** |
| Search Index Data Contributor | `8ebe5a00-799e-43f5-93ac-243d3dce84a7` | push documents; query |

Declared in the template rather than run as one-off `az role assignment create`,
for the reason `foundry.bicep:407` already gives: a grant that exists only in
someone's shell history does not survive a teardown.

⚠️ **Both are required, and the first is the non-obvious one.** `Search Index
Data Contributor` cannot read service statistics — the permission table gives
"Access quotas and service statistics" to Owner, Contributor and Search Service
Contributor only. SC-005's whole measurement depends on the role that looks like
the administrative one ([R7](../research.md)).

⚠️ **Owner is not enough**, again. Owner is a control-plane role here exactly as
it was on Cognitive Services: it can create the service and read keys, and it
cannot create an index or load a document.

### Validation

```bash
az bicep build -f infra/search.bicep
az deployment group what-if -g rg-ai300-rag -f infra/search.bicep -p callerPrincipalId=...
az deployment group create  -g rg-ai300-rag -n block5-search-001 -f infra/search.bicep -p callerPrincipalId=...
az deployment group create  -g rg-ai300-rag -n block5-search-002 -f infra/search.bicep -p callerPrincipalId=...
```

Deployed **twice**, like `foundry.bicep`. Re-runnability is a property this
repository now tests rather than hopes for.

---

## 2. Reading the envelope — before anything is indexed

```bash
TOKEN=$(az account get-access-token --scope https://search.azure.com/.default --query accessToken -o tsv)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<service>.search.windows.net/servicestats?api-version=2026-04-01" | python3 -m json.tool
```

Record, as numbers:

| Counter | Recorded | Compared against |
| --- | --- | --- |
| `storageSize` quota | ✅ | the published 50 MB |
| **`vectorIndexSize` quota** | ✅ | ⚠️ **nothing** — Learn's quota table has columns for Basic through L2 and **no Free column** |
| index / indexer / datasource counters | ✅ | the published 3 / 3 / 3 |

**This is the fact the source omits**, and reading it is the whole of SC-005. The
record must state whether the returned vector quota **confirms or contradicts**
the inference that the 50 MB service storage limit binds first. Either way it is
a new published number.

If the call returns `403`, the cause is the role split above, not the tier.

---

## 3. The index

Created by script over the data plane — an index is not an ARM resource and
cannot come from Bicep.

Schema per [data-model.md § 2–3](../data-model.md): key `chunk_id`, searchable
`content` and `heading`, filterable `note` / `token_count` / `corpus_commit`, and
`content_vector` as `Collection(Edm.Single)` at **3072** dimensions with an HNSW
profile using cosine.

One semantic configuration, `default`, with `heading` as the title field and
`content` as the content field.

**One index, four query shapes.** Nothing about the index differs between the
methods; only the query does (FR-007). That is what makes the comparison a
comparison, and what keeps the embedding bill paid once.

---

## 4. Ingestion — push, and why

Chunking and embedding happen **locally**; documents are pushed over the data
plane with an Entra ID token.

| | Push (chosen) | Indexer + integrated vectorization (rejected) |
| --- | --- | --- |
| Credentials | Entra ID token, no key anywhere | ⚠️ **needs a key-bearing connection string** — the Free tier grants no managed identity for indexer outbound connections |
| Runtime cap | none | 1–3 minutes (3–10 with a skillset) |
| Enrichment cap | not applicable | 20 transactions per indexer per day |

FR-003's downgrade clause therefore **stays dormant**: the credential-less
posture is preserved, not traded away. The rejected path is documented rather
than omitted — it is the path Learn's tutorials take, and knowing *why* it is
unavailable here is the examinable part (US2 scenario 3).

**Before pushing**, the corpus token distribution is measured with `tiktoken`
(local, free) and reported: total, per-note, and the chunk-count that follows
(FR-002). A recommended constant is not applied blind.

---

## 5. After indexing — the measured size

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<service>.search.windows.net/indexes/<index>/stats?api-version=2026-04-01"
```

Record `documentCount`, `storageSize`, `vectorIndexSize`, and compare
`vectorIndexSize` against the documented formula's prediction — for ~145 chunks
at 3072 dimensions, ≈1,8 MB (SC-006). A gap between predicted and actual is a
result, not an error to reconcile away.

---

## 6. Refusals are evidence

Any attempt the tier does not permit is captured **verbatim** (US2 scenario 4).
A refusal is the only direct measurement of a boundary, and this repository has
already built two features out of quoted error text.

Nothing here bills. The service is 0,00 €/day at every step above.
