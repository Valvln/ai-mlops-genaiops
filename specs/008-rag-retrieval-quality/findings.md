# Findings: what building Block 5 disproved

Recorded 2026-08-27/28 and 2026-09-19, across the sessions that redeployed
`infra/foundry.bicep`, created the free search service, indexed the corpus and
scored the four retrieval methods. Everything here was **measured, not reasoned
about** — each entry carries the command and the output that produced it.

Six of these contradict something the plan or a research note had settled before
building. That is why they live here and not in `research.md`: research recorded
what was decided **before**, and these are what building disproved.

**Status**: F1, F2, F3 and F4 are **recorded as corrections to the sourced
notes** — nothing to fix in code, the documentation was wrong or absent. F5 is
**fixed** in `score_retrieval.py`. F6 is a **defect in this feature's own spec**,
recorded rather than patched over.

Block 4's F1 (the account-level lock race) is **verified fixed and not reopened**:
`foundry.bicep` was deployed twice consecutively with a third child resource
chained in, and both runs returned `Succeeded`.

| Run | Template | Result |
| --- | --- | --- |
| `block5-001` | Foundry User + embedding deployment, chained | **Succeeded** |
| `block5-002` | same template, immediately after | **Succeeded — idempotent** |
| `block5-search-001` | new `search.bicep` | **Succeeded** |
| `block5-search-002` | same template, second run | **Succeeded — idempotent** |

---

## F1 — The Free tier publishes no vector quota, and neither does the service

**Severity**: SC-005's headline measurement returns nothing to measure. The
inference it was meant to settle is settled by absence instead.

`rag-vector-store-and-indexing.md` § 4 flagged that Learn's vector-quota table
has columns for Basic through L2 and **no Free column**, and proposed reading the
value off the service:

> The response carries `storageSize.quota` and `vectorIndexSize.quota`. Whatever
> it says is a new published number, either confirming the 50 MB inference or
> contradicting it.

It says neither.

```text
GET https://<service>.search.windows.net/servicestats?api-version=2025-09-01

"storageSize":     { "usage": 0, "quota": 52428800 },
"vectorIndexSize": { "usage": 0, "quota": null },
"documentCount":   { "usage": 0, "quota": null },
"indexesCount":    { "usage": 0, "quota": 3 }
```

**`vectorIndexSize.quota` is `null`.** Not zero, not a number — the field is
present and carries no quota. The Free tier exposes no vector budget through
either channel.

**Which is wrong**: neither, strictly. The note's inference — that the 50 MB
service storage limit binds first — is now supported, but by **elimination**
rather than by a published figure. That is a weaker form of evidence and the note
must say so, because "confirmed by the service" and "no competing limit exists"
are different claims.

`documentCount.quota` is `null` for a structural reason worth separating: the
published 10,000 is a limit **per indexer invocation**, and this feature runs no
indexer. Nothing caps documents on a free service except storage.

---

## F2 — The documented vector-index formula underestimates by 3×

**Severity**: anyone sizing a Free-tier vector index from the published formula
gets an answer three times too optimistic, and discovers it at the point of
refusal.

Learn's formula, quoted in `rag-vector-store-and-indexing.md` § 4:

```text
raw size = (number of documents) × (dimensions) × (size of data type)
```

For this corpus: 222 × 3072 × 4 B = **2 727 936 B ≈ 2,60 MB**. Measured after
ingestion:

```text
GET .../indexes/exam-notes/stats?api-version=2025-09-01

{ "documentCount": 222, "storageSize": 8832585, "vectorIndexSize": 8222516 }
```

| | Predicted | Measured | Ratio |
| --- | ---: | ---: | ---: |
| `vectorIndexSize` | 2 727 936 B | **8 222 516 B** | **3,01×** |
| per document | 12 288 B | **37 038 B** | 3,01× |

**Which is wrong**: the formula is incomplete rather than false. It prices the
vectors; the service also stores the HNSW graph that makes them searchable, and
that structure is not in the arithmetic. The note does quote an
`algorithm_overhead` multiplier, but publishes no value for it — so the formula
as given cannot be evaluated, and the figure a reader computes from it is the raw
size alone.

**Operative consequence**: at 39 786 B of total storage per document, the 50 MB
limit binds at roughly **1 300 chunks** of this shape, not the ~4 200 the raw
formula suggests.

---

## F3 — Index statistics report zero after a successful push

**Severity**: low, and dangerous in exactly this repository's recurring shape —
a check that reports the wrong thing while every call returns success.

All 222 documents were pushed with per-document success. Reading the index
statistics immediately afterwards:

```text
{ "documentCount": 0, "storageSize": 0, "vectorIndexSize": 0 }
```

A direct query against the same index, seconds later:

```python
SearchClient.search(search_text="*", include_total_count=True).get_count()
# 222
```

**Which is wrong**: neither — the documents were there, the statistics endpoint
lags. But the failure mode is block 4's F6 inverted: there, spans were accepted
with `HTTP 200` and never became queryable; here the data is queryable and the
statistics say it is absent. **The statistics endpoint is not a source of truth
about whether ingestion succeeded**, only about how much room it took, and only
once it catches up. Twelve hours later it reported the figures in F2.

---

## F4 — `disableLocalAuth` does not remove the keys, only their acceptance

**Severity**: a security property that reads stronger than it is.

`infra/search.bicep` sets `disableLocalAuth: true`, and the repository's posture
is stated as "no keys anywhere". The control plane disagrees:

```text
az search admin-key show --service-name <service> -g rg-ai300-rag
{ "primaryKey": "...", "secondaryKey": "..." }        # HTTP 200, keys returned
```

The data plane does not:

```text
curl -H "api-key: <primaryKey>" ".../indexes/exam-notes/docs/$count?api-version=2025-09-01"
HTTP 401
```

**Which is wrong**: the repository's own phrasing. `disableLocalAuth` disables
key **authentication**, not key **existence**. The secret material is still
provisioned, still rotatable, and still readable by any principal holding
`listAdminKeys` — Owner or Contributor. Flip the flag and those two strings work
immediately.

On a disposable learning service this is a curiosity. In production it is the
difference between a credential that cannot be used and a credential that has
been deleted, and only the second is a security property.

Related, by design rather than by discovery: `authOptions` reads back `null`,
because it and `disableLocalAuth` are mutually exclusive and a template setting
both does not deploy.

---

## F5 — The evaluator's metrics are not where the return value appears to put them

**Severity**: produced a results table that looked complete and answered none of
FR-011. **Fixed** in `rag-optimization/rag-block5/score_retrieval.py`.

`DocumentRetrievalEvaluator` returns a composite. The first version of the
scoring script averaged every numeric key at the top level and produced:

```text
| Method | document_retrieval | document_retrieval_score | document_retrieval_threshold |
| `keyword` | 0.472 | 0.472 | 0.500 |
```

One number per method, plus a threshold. The seven metrics the feature exists to
report are nested one level down:

```python
list(result.keys())
# ['document_retrieval', 'document_retrieval_score', 'document_retrieval_passed',
#  'document_retrieval_result', 'document_retrieval_reason',
#  'document_retrieval_status', 'document_retrieval_threshold',
#  'document_retrieval_properties']

list(result['document_retrieval_properties'].keys())[:7]
# ['ndcg@3', 'xdcg@3', 'fidelity', 'top1_relevance', 'top3_max_relevance',
#  'holes', 'holes_ratio']
```

**Which is wrong**: the measurement, and it was mine. The table was plausible —
four methods, four ascending numbers, an ordering that matched the expected one.
Nothing about it announced that `fidelity` and `holes_ratio` were missing. It is
the same defect this repository keeps meeting, arriving this time in the shape of
a green-looking results file.

**Verified separately**: the SDK's declared defaults are
`ground_truth_label_min=0, ground_truth_label_max=4`, read off
`inspect.signature` on version 1.18.3 — confirming `research.md` § R8 and the
reason FR-009 requires the range to be declared explicitly.

---

## F6 — One of the two control questions is not a control

**Severity**: a control that does not test what a control is for. Recorded, not
repaired: repairing it means re-pooling and re-labelling.

q21 asks: *«Which Azure OpenAI models support the Batch API, and what discount
does batch processing apply?»* It was chosen after verifying the corpus:

```text
grep -ril "Batch API" docs/exam-notes/     # no matches
```

That check was too narrow. `foundry-deployment-types.md` § 5 states:

> Global Batch and Data Zone Batch process asynchronous groups of requests at
> **50% less cost than Global Standard**, with a **24-hour target turnaround**.

which answers the second half of the question outright. The chunk is graded `2`,
and q21 scores `ndcg@3` 0.579–0.726 across the four methods — numbers that look
like a control being fooled and are nothing of the kind.

**Which is wrong**: the question, and by extension the spec's Edge Case
requiring "at least one control". It is satisfied by **q22** alone, which pooled
18 chunks, graded every one `0`, and produced `ndcg@3` **0.000** on all four
methods. One clean control remains, so the requirement holds; the set has one
fewer than it claims.

**The lesson is the grep.** Verifying a phrase (`"Batch API"`) is not verifying a
concept (`batch`). `grep -ril batch docs/exam-notes/` returns nine notes, and
running that first would have disqualified the question before it was written.

---

## F7 — RRF fusion ranked worse than its own vector leg

**Severity**: not a defect — a measurement that contradicts how hybrid search is
usually presented. Recorded because the plan expected the opposite.

| Method | ndcg@3 | fidelity |
| --- | ---: | ---: |
| `keyword` | 0.472 | 0.646 |
| `vector` | **0.579** | 0.816 |
| `hybrid` | **0.545** | 0.816 |
| `hybrid_semantic` | 0.601 | 0.843 |

Learn asserts hybrid with semantic ranking wins «in benchmark testing» and
publishes no margin. The top of the ordering holds. The middle does not: plain
`vector` beats `hybrid` on `ndcg@3` by 0.034 and ties it on `fidelity`, so adding
the BM25 leg and fusing with RRF made the ranking **worse** than the vector query
alone on this corpus.

**Which is wrong**: neither. Learn's claim is about `hybrid_semantic`, which did
win. What is contradicted is the looser framing — common in tutorials — that
hybrid dominates both of its legs. It does not, at least not here.

**The margin is the new fact.** `hybrid_semantic` over `keyword` is +0.129
(**+27 %**); over `vector`, the next best, **+0.022 (under 4 %)**. On a corpus
this small and homogeneous, the whole semantic-ranking stage buys less than the
gap between keyword and vector search.

⚠️ 22 questions, 222 chunks, one author, mixed-provenance labels. A measurement,
not a benchmark.

---

## F8 — The plan's corpus estimate was 35 % low, and the plan knew it might be

**Severity**: none — this is FR-002 working as designed. Recorded because the
gap is large enough to be worth quoting.

`data-model.md` § 2 predicted ~55 000 tokens and **≈145 chunks**. Measured with
`tiktoken`/`o200k_base` before cutting:

```text
18 notes, 65688 tokens, mean 3649 tokens/note
chunks: 222  (38 sections exceeded the cap and were windowed)
tokens to embed: 72711 (1.11x the corpus, from the overlap)
```

The service then billed **73 249** tokens against `tiktoken`'s 72 711 — a
**0,74 % underestimate**, one-directional, worth knowing before a local count is
used to predict a bill.

**Which is wrong**: the estimate, and it was never presented as anything else.
FR-002 exists precisely so the measurement precedes the cut rather than
justifying it afterwards.
