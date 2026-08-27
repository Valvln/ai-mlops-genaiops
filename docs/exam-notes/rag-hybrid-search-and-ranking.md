# Hybrid search and semantic ranking — RRF, the L2 reranker, and three score ranges

**Status: documented, not measured.** Read from the Microsoft Learn pages under
*Sources* on **2026-08-27**, before the block 5 plan freezes.

The headline for this block: **semantic ranking runs on the Free tier.** The
tier article says so — *«Semantic ranker: runs on the Free tier but not
recommended for large workloads»* — and the billing article says the free plan is
*«available on all pricing tiers»*. So the full ladder — keyword → vector →
hybrid → hybrid + semantic — is reachable at **0,00 €** of search cost. That is
the fact the block 5 spec is built on, and § 5 is the one caveat attached to it.

---

## 1. What hybrid search is, precisely

> «Hybrid search is a **single query request** configured for both full-text and
> vector queries… Runs full-text search and vector search **in parallel**. Merges
> results from each query by using Reciprocal Rank Fusion (RRF).»

One request, two or more executions, one result set. Not two round trips merged
in application code.

Why it wins is stated as a division of labour, not as magic:

> «The advantage of vector search is finding information that's **conceptually
> similar** to your search query, even if there are no keyword matches in the
> inverted index. The advantage of keyword or full-text search is **precision**,
> with the ability to apply optional semantic ranking… Some scenarios, such as
> querying over **product codes, highly specialized jargon, dates, and people's
> names**, perform better with keyword search because it can identify exact
> matches.»

That list is the answer to "why not just use vectors": an embedding of a part
number is near the embeddings of other part numbers. Exactness is not a thing
vectors are good at, and it is exactly what BM25 does.

Learn's claim about the combination is deliberately unquantified on this page:

> «Benchmark testing on real-world and benchmark datasets indicates that **hybrid
> retrieval with semantic ranker** offers significant benefits in search
> relevance.»

⚠️ **No NDCG table is published on the hybrid overview page.** The ranking page
repeats the conclusion — *«Try hybrid queries with semantic ranking. In benchmark
testing, this combination consistently produced the most relevant results»* —
also without numbers. The ordering (hybrid+semantic > hybrid > single method) is
documented; the *margin* is not. Anyone quoting a specific percentage is quoting
a blog post, not the documentation. **Measuring that margin on one's own corpus
is precisely what `rag-retrieval-evaluation.md` is for.**

---

## 2. RRF — the formula, and the constant that collides

> «The score is calculated as **`1/(rank + k)`**, where `rank` is the position of
> the document in the list and `k` is a constant. Experiments show the algorithm
> performs best when you set `k` to a small value, such as **60**. This `k` value
> is a constant in the RRF algorithm and **entirely separate from the `k` that
> controls the number of nearest neighbors**.»

Two `k`s in one query, meaning different things. Learn calls out the collision
itself, which is a strong hint it is exam material.

The procedure:

1. Run the queries in parallel; each produces its own ranked list.
2. Score each document `1/(rank + k)` **per list**.
3. **Sum** a document's scores across the lists it appears in.
4. Sort by the sum.

Note what step 2 discards: **the original relevance scores**. RRF consumes
*positions*, not scores. This is the reason it works at all —

> «Each algorithm has its own range and magnitude.»

— BM25 has no upper bound, cosine-derived vector scores live in 0.333–1.00, and
averaging them would be meaningless. Rank is the only commensurable quantity the
two methods share.

### How many executions

| Query | Executions |
| --- | --- |
| full-text + 1 vector query | 2 |
| full-text + 1 vector query over 2 vector fields | 3 |
| full-text + 2 vector queries over 5 vector fields | 11 |

This matters because the RRF score's ceiling depends on it: *«Upper limit is
bounded by the number of queries being fused, with each query contributing a
maximum of approximately `1/k`… merging three queries produces higher RRF scores
than if only two search results are merged.»* **RRF scores are not comparable
across queries of different shapes.**

### Weighting

Vector queries accept a `weight` multiplier — default `1.0`, applied to the
initial score before RRF. Learn's worked example:

| Match | Position | `@search.score` | weight | weighted |
| --- | --- | --- | --- | --- |
| vector results one | 1 | 0.8383955 | 0.5 | 0.41919775 |
| vector results two | 5 | 0.81514114 | 2.0 | 1.63028228 |
| BM25 results | 10 | 0.8577363 | — | 0.8577363 |

Only vector queries can be weighted; the text side has no counterpart. To see
the components, add `"debug": "vector"` (or `"semantic"`, or `"all"`) to the
request.

---

## 3. Semantic ranking — an L2 pass over 50 results

Semantic ranker is **query-side only** and adds three things:

1. **L2 re-ranking** over an existing BM25- or RRF-ranked result set, using
   *«multilingual, deep learning models adapted from Microsoft Bing»*.
2. **Captions and answers** extracted from the index.
3. **Query rewrite** (optional), expanding the query into up to 10 variants.

### The pipeline, and its hard ceiling

> «The semantic ranker starts with a BM25-ranked result from a text query or an
> RRF-ranked result from a vector or hybrid query. The reranking exercise **uses
> only text**. Even if results include more than 50 results, **only the top 50
> results progress to semantic ranking**.»

⚠️ **50 is a ceiling, not a default.** The reranker cannot rescue a document that
L1 ranked 51st. This produces the single most practical piece of query advice in
the documentation:

> «If you're using semantic ranker, set `k` to **50** to maximize its inputs.»

And the limitation stated in as many words:

> «What semantic ranker *can't* do is rerun the query over the entire corpus…
> Semantic ranking **reranks the existing result set**.»

So retrieval quality caps reranking quality. Semantic ranking is a precision
instrument applied to whatever recall the first stage achieved — which is why
`rag-retrieval-evaluation.md` measures the two separately.

### Summarization, and why field order in the configuration matters

Each document is summarized before scoring, from fields named in the **semantic
configuration**:

| Semantic field | Token limit |
| --- | --- |
| `title` | 128 tokens |
| `keywords` | 128 tokens |
| `content` | remaining tokens |

Per document the summarization model accepts **up to 2,000 tokens** (~10
characters per token), and the summary string passed to the ranker is at most
**2,048 tokens** (raised from 256 in November 2024).

> «The system trims excessively long strings… This trimming exercise is why it's
> important to add fields to your semantic configuration **in priority order**.
> If you have very large documents with text-heavy fields, the system **ignores
> anything after the maximum limit**.»

Silent truncation governed by the order of a list in the index definition. On a
chunked index this is mostly moot — chunks are small by construction — which is
one more argument for chunking even when documents fit.

### Captions and answers are extractive

> «Captions and answers are **always verbatim text from your index**. There's no
> generative AI model in this workflow that creates or composes new content.»

A caption cannot hallucinate. It can be irrelevant, but it cannot be invented —
worth holding next to the block 4 finding that a groundedness evaluator's
default threshold *«promotes a confident fabrication»*.

### Where it helps and where it does not

> «The language models in semantic ranker work best on searchable content that is
> **information-rich and structured as prose**. A knowledge base, online
> documentation, or documents that contain descriptive content see the most
> gains.»

Corollary: tables of part numbers, code, and short structured records gain little.

---

## 4. ⚠️ Three scores, three ranges, and two property names

The single densest exam target in this area:

| Method | Property | Algorithm | Range |
| --- | --- | --- | --- |
| full-text | `@search.score` | **BM25** | **no upper limit** |
| vector | `@search.score` | HNSW / eKNN + similarity metric | **0.333 – 1.00** (cosine); 0–1 (euclidean, dotProduct) |
| hybrid | `@search.score` | **RRF** | bounded by the number of fused queries, ~`1/k` each |
| semantic | **`@search.rerankerScore`** | semantic ranker | **0.00 – 4.00** |

Three different quantities share `@search.score`; the reranker gets its own
property. And the ordering is:

> «Semantic ranking occurs **after** RRF merging of results. Its score is always
> reported **separately** in the query response.»

The `@search.rerankerScore` scale is defined, not arbitrary:

| Score | Meaning |
| --- | --- |
| 4.0 | highly relevant, answers the question completely |
| 3.0 | relevant but lacks details |
| 2.0 | somewhat relevant; partial answer |
| 1.0 | related, answers a small part |
| 0.0 | irrelevant |

⚠️ And the warning against over-fitting a threshold to it:

> «For any given query, the distributions of `@search.rerankerScore` can exhibit
> slight variations due to conditions at the infrastructure level. **Ranking model
> updates can also affect the distribution.** For these reasons, if you're writing
> custom code for minimum thresholds… **don't make the limits too granular**.»

This is the same shape as the block 4 finding on evaluator thresholds: a number
that looks like a measurement is the output of a model that can be replaced under
you. A threshold of 2.0 is defensible; 2.37 is a fiction with three significant
digits.

---

## 5. Billing — free on all tiers, until it isn't

| Plan | Terms | Availability |
| --- | --- | --- |
| **Free** (default) | «Provides a monthly free request allowance. After the free allowance is consumed, semantic ranker requests **return a billing error**.» | **All pricing tiers** |
| Standard | pay-as-you-go after the free allowance | **Requires Basic or higher** |

Every service is enrolled in the free plan by default. The consequences for this
repository:

- The Free search tier can only ever be on the free semantic plan — the standard
  plan is not available below Basic. **There is no way to accidentally start
  paying for semantic ranking from a Free service.** Exhaustion produces an
  error, not a charge. This is the rarest property in this whole project: a
  premium feature with a hard stop instead of a meter.
- ⚠️ **The size of the monthly allowance is not published on the Learn concept
  pages** — they say «a monthly free request allowance» without a number. The
  Azure retail price list carries a `Free queries` meter at **0,00 €/1K** and a
  `Semantic Ranker queries` meter at **0,8786 €/1K** for the standard plan
  (northeurope, EUR, read 2026-08-27). The threshold between them is a figure to
  confirm on the pricing page or by measurement, not to assume.

What is billable, stated precisely:

> «Charges for semantic ranker occur when query requests include
> `queryType=semantic` **and the search string isn't empty**… If your search
> string is empty (`search=*`), you **aren't charged**, even if the `queryType`
> is set to semantic.»

Semantic throttling is per search unit and the published table **starts at
Basic** — Free has no row, consistent with having no partitions or replicas.

---

## 6. Assembling the query

```http
POST https://{service}.search.windows.net/indexes/{index}/docs/search?api-version=2026-04-01
{
  "search": "historic hotel walk to restaurants and shopping",
  "vectorQueries": [
    { "kind": "vector", "vector": [ ... ], "fields": "DescriptionVector",
      "k": 50, "exhaustive": true, "oversampling": 20 }
  ],
  "select": "HotelId, HotelName, Description",
  "filter": "...",
  "vectorFilterMode": "postFilter",
  "queryType": "semantic",
  "semanticConfiguration": "my-semantic-config",
  "top": 10
}
```

- `queryType=semantic` + `semanticConfiguration` are the only additions the
  reranker needs; *«Semantic ranking is optional. If you aren't using this
  feature, remove the last three lines.»* The ladder is four requests differing
  by a handful of properties, which is what makes the comparison cheap.
- **`orderby` destroys the ranking.** *«Explicit sort orders override
  relevance-ranked results, so if you want similarity and BM25 relevance, omit
  sorting in your query.»*
- Filters run against structures separate from both the inverted index and the
  vector index. `vectorFilterMode` chooses pre- or post-filter; *«If you're using
  semantic ranker, you probably want post-filtering as the last step, but you
  should test to confirm.»*
- A vector field is never `filterable`; filter on an accompanying text or
  numeric field.
- Defaults: 50 results for full text, `k` for vector, `top` decides the hybrid
  response. Full-text recall caps at **1,000 matches** (`maxTextRecallSize`).
- Semantic ranker applies synonym maps automatically for fields that have them
  and are in the semantic configuration.

---

## 7. What this note would cost to verify

**The entire ladder is free on Search.** Four query shapes against one index:
BM25 only, vector only, hybrid, hybrid + semantic. Search bills 0,00 €/hour on
Free and semantic queries fall under the free plan with a hard stop.

| Claim | Verifiable? | Cost |
| --- | --- | --- |
| The four-step ladder changes the ranking | yes, and it is the point of the block | 0,00 € on Search; one embedding per query |
| RRF `1/(rank+60)` reproduces `@search.score` | yes — compute it by hand from `debug: all` | 0,00 € |
| Only the top 50 reach the reranker | yes — a document ranked 51st by L1 stays down | 0,00 € |
| Semantic free allowance size (§ 5) | yes, but only by exhausting it | 0,00 € — the wall is an error, not a bill |
| The *margin* hybrid+semantic gains | **only by measuring** — Learn publishes no number | `rag-retrieval-evaluation.md` |

The last row is the one worth stating loudly. Learn asserts an ordering without a
magnitude; this repository's whole method is to produce the magnitude. That
measurement will not contradict the source — it will supply what the source
omits, which is the other useful outcome the amended constitution anticipates.

---

## Sources

- [Hybrid search overview](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview) — read 2026-08-27; §§ 1, 6
- [Hybrid search scoring (RRF)](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking) — read 2026-08-27; §§ 2, 4
- [Semantic ranking overview](https://learn.microsoft.com/en-us/azure/search/semantic-search-overview) — read 2026-08-27; §§ 3, 4, 5
- [Enable or disable semantic ranker billing](https://learn.microsoft.com/en-us/azure/search/semantic-how-to-enable-disable) — read 2026-08-27; § 5
- [Choose a pricing model and service tier](https://learn.microsoft.com/en-us/azure/search/search-sku-tier) — read 2026-08-27; § 5, Free-tier feature table
- [Vector relevance and ranking](https://learn.microsoft.com/en-us/azure/search/vector-search-ranking) — read 2026-08-27; § 4, score ranges
- Azure Retail Prices API, `serviceName eq 'Azure Cognitive Search'`, northeurope, EUR — read 2026-08-27; § 5 meters
- `rag-vector-store-and-indexing.md` § 3 — where the vector half of the hybrid comes from
- `rag-retrieval-evaluation.md` — how the ladder gets a number attached to it
