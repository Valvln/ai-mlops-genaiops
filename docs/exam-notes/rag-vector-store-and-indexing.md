# Azure AI Search as a vector store — indexing, algorithms, and what the Free tier allows

**Status: documented, not measured.** No search service has ever existed in this
subscription. Every claim below comes from the Microsoft Learn pages under
*Sources*, read on **2026-08-27**. This note is written *before* the block 5 plan
freezes, as the constitution now requires (§ Development Workflow, *Sourced
Research Before the Plan Freezes*, adopted 1.1.0).

Two claims in here are the ones most likely to be contradicted by measurement,
and they are marked ⚠️ **to verify** where they appear:

1. Learn publishes **no vector-index quota for the Free tier** — the table skips
   the column entirely. What binds instead is unclear from the documentation.
2. Managed identity for indexer connections is **not available on Free**, which
   collides with this repository's credential-less habit.

---

## 1. What a vector store is here

Azure AI Search is not a separate vector database bolted on. A vector field is a
field type inside an ordinary search index, sitting next to text and numeric
fields in the same document:

> «In a search index, vector fields containing embeddings coexist with textual
> and numerical fields.»

Internally, the physical structures of one index are three:

| Structure | Backs | Consumes |
| --- | --- | --- |
| Raw content | retrieval of non-tokenized values | disk storage |
| Inverted indexes | `searchable` text fields (BM25) | disk storage |
| **Vector indexes** | `searchable` vector fields | disk **and**, for HNSW, memory quota |

That third row is the whole cost model of vector search on a small tier, and § 4
is about it.

**Availability is not the constraint.** Learn is explicit:

> «Vector search is available in **all regions** and on **all tiers** at no extra
> charge. However, generating embeddings or using AI enrichment for vectorization
> might incur charges from the model provider.»

So the Free tier can hold vectors. What it cannot hold is *many* of them, and
the embeddings that fill them are billed by Foundry, not by Search.

---

## 2. The schema pieces, and which one is which

A vector-capable index declares a `vectorSearch` section with four collections.
Getting the vocabulary straight matters because three of the four are easy to
confuse:

| Element | What it declares | Referenced by |
| --- | --- | --- |
| `algorithms` | HNSW or exhaustive KNN, plus their parameters and the similarity `metric` | a profile |
| `vectorizers` | which embedding model encodes a **query string** at query time | a profile |
| `compressions` | scalar or binary quantization settings | a profile |
| `profiles` | names one algorithm, optionally one vectorizer and one compression | **the field** |

The field points at a *profile*; the profile points at everything else. A vector
field also carries `dimensions`, which must match the embedding model's output
exactly (maximum 4,096 on every tier).

### The rule that makes or breaks the index

> «Vector queries execute against an embedding space consisting of vectors
> generated from **the same embedding model**. Generally, the input value within
> a query request is fed into the same machine learning model that generated
> embeddings in the vector index.»

Index-time and query-time embeddings must come from the same model. A
`vectorizer` in the index is how you make that structural instead of a
convention someone has to remember — the service encodes the query itself, from
the model named in the index. Encoding the query in application code works too,
and moves the guarantee into the application's hands.

### Integrated vectorization

Two ways to fill a vector field:

- **Integrated** — an indexer + data source + skillset chunk the source content
  and call an embedding model. Search makes the calls; you supply endpoint and
  connection information.
- **External (push)** — generate embeddings yourself and push pre-vectorized
  documents into the index.

The integrated path is the one the exam describes; the push path is the one that
survives the Free tier's indexer limits (§ 5).

---

## 3. HNSW or exhaustive KNN — and why the small case inverts the default

| | Exhaustive KNN | HNSW |
| --- | --- | --- |
| What it does | brute-force scan of the whole vector space | approximate nearest neighbor over a hierarchical graph |
| Result | **exact** `k` nearest neighbors | approximate, high recall |
| Memory | loaded in pages at query time | **all data points resident in memory** |
| **Vector quota** | **does not consume it** | **consumes it** |
| Tunable | no | `m`, `efConstruction`, `efSearch`, `metric` |
| Query-time override | — | supports `"exhaustive": true` |

Learn's own recommendation:

> «Exhaustive KNN is computationally intensive, so use it for **small to medium
> datasets** or when the need for precision outweighs the need for query
> performance. Another use case is **building a dataset to evaluate the recall of
> an ANN algorithm**, as exhaustive KNN can be used to build the ground truth set
> of nearest neighbors.»

And the asymmetry that is exam-shaped:

> «Fields that specify HNSW also support exhaustive KNN using the query request
> parameter `"exhaustive": true`. However, **fields indexed for `exhaustiveKnn`
> don't support HNSW queries** because the extra data structures that enable
> efficient search don't exist.»

**One direction only.** HNSW can be asked to behave exhaustively per query;
exhaustive-KNN fields can never be asked to behave like HNSW without reindexing.
So an index built on HNSW keeps both options; an index built on `exhaustiveKnn`
has thrown one away.

That asymmetry, plus the quota row, is the design decision this block faces: on
a corpus small enough for the Free tier, exhaustive KNN is **exact, free of
vector quota, and irreversible**; HNSW is approximate, consumes the quota whose
size Learn does not publish for Free, and keeps the exhaustive option open. The
second is the more informative choice for a learning exercise *because* it can
produce both answers and be compared against itself.

### HNSW parameters

| Parameter | Governs | Learn's stated default / range |
| --- | --- | --- |
| `m` | bi-directional links per new vector | overhead ≈ 8–10 bytes per document per link |
| `efConstruction` | candidate connections considered at index time | **default 400**, range **100–1,000** |
| `efSearch` | length of the candidate priority queue at query time | — |
| `metric` | similarity function | see below |

### Similarity metrics

| Metric | Description | When |
| --- | --- | --- |
| `cosine` | angle between two vectors, unaffected by length | **Azure OpenAI embedding models — Learn says specify `cosine`** |
| `dotProduct` | magnitudes *and* angle; identical to cosine for normalized vectors, slightly faster | normalized vectors, when latency matters |
| `euclidean` (l2) | length of the difference vector | — |

⚠️ **`@search.score` is not the cosine.** Learn:

> «For the `cosine` metric, the calculated `@search.score` **isn't the cosine
> value**… the `@search.score` is defined as `1 / (1 + cosine_distance)`.»

Range for a pure vector query is therefore **0.333 – 1.00**, not −1 to 1. Anyone
thresholding on "cosine similarity above 0.8" against this field is thresholding
on a different quantity. The conversion back is
`cosineDistance = (1 - score) / score`.

This is the same class of trap as `@search.rerankerScore` (0–4) and BM25 (no
upper limit) — three scores, three ranges, one property name. See
`rag-hybrid-search-and-ranking.md` § 4.

---

## 4. Vector index size, and the quota that is a memory constraint

The estimate Learn gives:

```
raw size      = (number of documents) × (dimensions) × (size of data type)
vector index  = raw_size × (1 + algorithm_overhead) × (1 + deleted_docs_ratio)
```

| EDM type | Bytes per dimension |
| --- | --- |
| `Collection(Edm.Single)` | 4 |
| `Collection(Edm.Half)` | 2 |
| `Collection(Edm.Int16)` | 2 |
| `Collection(Edm.SByte)` | 1 |

HNSW overhead falls as dimensionality rises, which is counter-intuitive and
worth remembering:

| Dimensions | `m` | Overhead |
| --- | --- | --- |
| 96 | 4 | 20% |
| 200 | 4 | 8% |
| 768 | 4 | 2% |
| 1536 | 4 | 1% |
| 3072 | 4 | 0.5% |

> «As dimensionality increases, the memory overhead percentage decreases… the
> raw size of the vectors increases while the other data structures, which store
> graph connectivity information, remain a fixed size for a given `m`.»

**Storage quota and vector quota are different resources.** Storage is disk and
covers every index, vector or not. Vector index size is **memory** — the amount
needed to hold all HNSW graphs resident. A service can be far from its storage
limit and still refuse to index because vector quota is full, and the failure
mode is stated plainly: *«Further indexing attempts once the limit is exceeded
result in failure.»*

Also worth knowing before estimating disk: *«Vector indexes on disk take up
about three times more space than vector indexes in memory.»*

### ⚠️ To verify — the Free tier's vector quota is not published

The vector-quota table in the limits article has columns for Basic, S1, S2,
S3/HD, L1 and L2. **There is no Free column**, in any of the four
service-creation-date rows. The article says the quota is enforced *per
partition*, and elsewhere that *«Free services don't have fixed partitions or
replicas and share resources with other subscribers.»*

So the documentation states that vector search runs on all tiers, and does not
state how much vector index a Free service may hold. The plausible reading is
that the **50 MB service storage limit** binds first, but that is inference, not
a documented figure.

This is measurable for free, and should be a success criterion of the feature:

```bash
# data-plane call against the free service; usage and quota are in bytes
GET https://{service}.search.windows.net/servicestats?api-version=2026-04-01
```

The response carries `storageSize.quota` and `vectorIndexSize.quota`. Whatever
number comes back is the first fact in this block that Learn could not supply —
either confirming the 50 MB inference or contradicting it. Under the amended
constitution, a contradiction is a finding, not a correction.

---

## 5. What the Free tier actually gives

Read this table before sizing anything. Every figure is from the limits article.

| Resource | Free | Basic | Note |
| --- | --- | --- | --- |
| Services per subscription | **1** | 16 per region | one only, ever |
| Storage | **50 MB** | 15 GB per partition | shared infrastructure, no scale-up |
| Partitions / replicas | **N/A** | 3 / 3 | no SLA on Free |
| Indexes | **3** | 5 or 15 | |
| Indexers / data sources / skillsets | **3** each | 5 or 15 | max 30 skills per skillset |
| Documents per indexer invocation | **10,000** | limited only by max docs | |
| Max source file (blob-like) | **16 MB** | 16 MB | |
| Max characters extracted per file | **256,000** | 512,000 | ⚠️ silent truncation |
| Indexer max run time | **3 min blob / 1 min other**; 3–10 min with a skillset | 2 or 24 hours | |
| Indexer invocation frequency | **once every 180 s** | 5-min schedule | |
| AI-enrichment transactions | **20 free per indexer per day** | — | reset the indexer to reset the count |
| Simple fields per index | 1,000 | **100** | Basic is the *only* tier with the lower limit |
| Max dimensions per vector field | 4,096 | 4,096 | same everywhere |
| Synonym maps | 3 | 3 | 5,000 rules per map on Free |

Footnote worth quoting, because it is a data-loss risk for a study environment:

> «A free search service **might be deleted after extended periods of
> inactivity** to make room for more services.»

An environment that deletes itself is, for once, aligned with this repository's
teardown policy — but it also means nothing built on Free can be assumed to
still exist after a two-week absence. It is not a substitute for the template.

### Features that do **not** work on Free

From the tier article's feature-availability table:

| Feature | On Free |
| --- | --- |
| **Managed or trusted identities for outbound (indexer) access** | **Not available** |
| Customer-managed encryption keys | Not available |
| IP firewall rules | Not available |
| Private endpoint (inbound) | Not available |
| Private endpoint (outbound, indexer → other Azure resources) | Not available |
| Availability zones | Not available |
| AI enrichment | «Runs on the Free tier but **not recommended for large workloads**» |
| **Semantic ranker** | «**Runs on the Free tier** but not recommended for large workloads» |

⚠️ **The first row is a direct collision with this repository's practice.** Every
data connection built so far is credential-less: the feature 004 datastore was
built specifically so that no key is cached in the vault, and `foundry.bicep`
sets `disableLocalAuth: true` for the same reason. On a Free search service, an
indexer reaching Azure Blob Storage **cannot** use a managed identity — it needs
a connection string carrying a key.

Three ways out, and the choice belongs in the spec, not in the code:

1. **Don't use an indexer.** Chunk and embed locally, push documents to the index
   over the data plane. Entra ID authentication to the *search service* is
   unaffected by the tier — the restriction is on the indexer's **outbound** leg.
   This also sidesteps the 1–3 minute indexer runtime and the 20-transaction
   enrichment cap.
2. Use an indexer with a key-bearing connection string, and record it as a
   deliberate downgrade forced by the tier.
3. Pay for Basic. Excluded by the cost constraint (`rag-cost-model.md` § 1).

Option 1 is the only one that keeps the repository's credential posture intact,
and it costs a chunking script that this block wants to write anyway. The last
row of the table is equally load-bearing in the other direction: **semantic
ranking is not blocked by the Free tier**, so the whole hybrid + semantic
comparison is reachable at zero search cost.

---

## 6. Making vectors fit in 50 MB

Learn's four levers, in its own order of preference — *«We recommend built-in
quantization because it compresses vector size in memory and on disk with
minimal effort»*:

| Lever | Effect |
| --- | --- |
| **Scalar or binary quantization** | float32/float16 → int8 (scalar) or byte (binary); reduces memory *and* disk, «with no degradation of query performance», offset by rescoring and oversampling against uncompressed embeddings |
| **Truncate dimensions (MRL)** | `truncateDimension` on `text-embedding-3` models, which are trained with Matryoshka Representation Learning to stay meaningful at lower dimensionality |
| **Narrow data types** | float16 / int16 / int8 / byte — needs an embedding model that emits them, except recasting float32 → float16 |
| **`stored: false`** | drops the separate copy kept for *returning* vectors in responses: «reduce overall per-field disk storage by **up to 50 percent**» |

They combine. Learn's published sample measurements on one corpus:

| Index | Storage | Vector size |
| --- | --- | --- |
| baseline | 21.3613 MB | 4.8277 MB |
| scalar compression | 17.7604 MB | 1.2242 MB |
| narrow types | 16.5567 MB | 2.4254 MB |
| no `stored` | 10.9224 MB | 4.8277 MB |
| **all options** | **4.9192 MB** | **1.2242 MB** |

Read against a 50 MB service: the baseline index is **43% of the entire Free
tier** and the fully-optimized one is **10%**. That single comparison decides
whether a corpus fits, and it is the reason this block can demonstrate
quantization for free — the constraint makes the feature necessary rather than
decorative.

⚠️ Two mechanical constraints: *«Define all of these options on an empty index»*
— compression and storage settings are not retrofittable, so an index built
without them must be rebuilt. And rescoring/oversampling *«are specific features
of built-in quantization of float32 or float16 fields and can't be used on
embeddings that undergo custom quantization»* — quantizing in your own code
forfeits the correction step.

---

## 7. What this note would cost to verify

| Claim | Cost to check | Blocked by |
| --- | --- | --- |
| Free service creates, one per subscription | **0,00 €** | nothing |
| `servicestats` vector and storage quota (§ 4) | **0,00 €** | nothing — one GET |
| HNSW vs exhaustive KNN on the same corpus | **0,00 €** on Search; embeddings billed by Foundry | needs both indexes, and Free allows 3 |
| Quantization storage reduction (§ 6) | **0,00 €** on Search | needs a second index, and re-embedding is re-billed |
| Indexer with managed identity refused on Free | **0,00 €** | nothing — the refusal *is* the evidence |
| Anything on Basic | **2,13 €/day and it does not stop** | the cost constraint |

The embedding calls are the only real spend, and they are token-priced —
`rag-cost-model.md` § 3 carries the rate. Nothing in this note requires a
resource that bills at rest, which is why the Free tier is a constraint worth
accepting rather than a compromise.

---

## Sources

- [Vector search overview](https://learn.microsoft.com/en-us/azure/search/vector-search-overview) — read 2026-08-27; §§ 1, 2
- [Vector relevance and ranking](https://learn.microsoft.com/en-us/azure/search/vector-search-ranking) — read 2026-08-27; § 3
- [Vector index size limits](https://learn.microsoft.com/en-us/azure/search/vector-search-index-size) — read 2026-08-27; § 4
- [Service limits for tiers and SKUs](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity) — read 2026-08-27; §§ 4, 5
- [Choose a pricing model and service tier](https://learn.microsoft.com/en-us/azure/search/search-sku-tier) — read 2026-08-27; § 5
- [Choose vector optimization](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-configure-compression-storage) — read 2026-08-27; § 6
- `rag-chunking-strategies.md` — what gets embedded before any of this applies
- `rag-hybrid-search-and-ranking.md` § 4 — the three score ranges
- `rag-cost-model.md` — the euros behind § 7
