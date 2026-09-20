# Contract — the four retrieval methods and how they are scored

Covers **User Story 1**, FR-008 to FR-014, SC-001 to SC-004.

---

## 1. The four methods

One index, one embedded corpus, one embedding per query, four query shapes. Top
**10** returned for each.

| Method | `search` | `vector_queries` | `query_type` | Ranked by |
| --- | --- | --- | --- | --- |
| `keyword` | query text | — | `simple` | BM25, `@search.score` |
| `vector` | — | one `VectorizedQuery`, k=10 | — | cosine similarity, `@search.score` |
| `hybrid` | query text | same vector | `simple` | **RRF**, `@search.score` |
| `hybrid_semantic` | query text | same vector | `semantic` + `semantic_configuration_name` | **L2 reranker**, `@search.rerankerScore` |

Each result row records the score **and the property it came from**
([data-model.md § 5](../data-model.md)).

⚠️ **Three incompatible score ranges arrive under two property names.** BM25 is
unbounded, cosine similarity is 0–1, RRF is a sum of `1/(rank + 60)` terms — all
three surface as `@search.score`. Semantic reranking surfaces as
`@search.rerankerScore`, 0–4. Four columns of these numbers side by side is a
table that invites exactly one wrong conclusion.

**Raw scores are never compared across methods.** The comparison is made on the
metrics in § 3, which are computed from *ordering and labels* and are
scale-free.

⚠️ Two different things are called **k**: the vector query's `k` (how many
neighbours to fetch) and RRF's constant `k = 60` (the rank discount). They are
unrelated.

⚠️ The semantic reranker's L2 pass reads **at most the top 50** of the first-stage
result set. At top-10 this does not bind, and it would if the run were widened.

---

## 2. Ordering — retrieval runs before labelling

```text
index → run all four → pool the union → label the pool → score
```

Labels are built by **pooling**: the union of chunks any method returned is what
gets a judgment ([research.md § R9](../research.md)). Label a set chosen in
advance, and every method surfaces unjudged documents — `holes_ratio` then
measures label coverage rather than retrieval quality, and the comparison
measures the wrong thing while looking healthy.

The runs are stored, so a label correction re-scores **without re-querying and
without re-embedding**. Changing the retrieval method costs nothing; that is the
cheap axis, and it is the axis this feature varies (FR-005 scenario 5).

---

## 3. Scoring

`DocumentRetrievalEvaluator`, from `azure-ai-evaluation >= 1.18.3, < 2`.

```python
DocumentRetrievalEvaluator(
    ground_truth_label_min=0,   # explicit — SDK default is 0, Learn's example passes 1
    ground_truth_label_max=3,   # explicit — SDK default is 4, Learn's example passes 5
)
```

Inputs, per question:

```python
retrieval_ground_truth = [{"document_id": "<chunk_id>", "query_relevance_label": 0..3}, ...]
retrieved_documents    = [{"document_id": "<chunk_id>", "relevance_score": <the ordering score>}, ...]
```

**No judge model. No model call. No `deployment_name`.** The evaluator is
arithmetic over human labels — which is why block 4's F5 (a default threshold
promoting a confident fabrication) cannot recur in this form.

⚠️ **The declared label range is not decoration.** `fidelity` weights labels over
`range(min + 1, max + 1)`; declaring 0–4 while using 0–3, or accepting the
default while labelling 1–5, silently reweights the metric instead of raising an
error. FR-009 exists for this, and the SDK's defaults disagreeing with the
documentation's own example is what makes it a live risk rather than a
hypothetical one.

### Results are read from the return value

Directly, in-process. **Not** through the trace store (FR-014). Block 4's F6 is
closed as a known limitation, not fixed: spans are accepted, acknowledged with
`HTTP 200` and `Items accepted`, and then do not become queryable — its token
counter reported 3 of ~13 calls, failing toward under-reporting. Anything read
back through that store inherits the loss. This feature does not route its
results through it.

---

## 4. What is reported

Per method, in one table (SC-001):

| Metric | Shape | Role |
| --- | --- | --- |
| `ndcg@3` | ranking | FR-011's ranking-shaped metric |
| `fidelity` | recall | FR-011's recall-shaped metric |
| `xdcg@3`, `top1_relevance`, `top3_max_relevance` | ranking | reported, secondary |
| `holes`, `holes_ratio` | **label sanity** | FR-012's gate |

**`holes_ratio` gates the table.** High means documents were retrieved that
nobody judged — the comparison is then declared unreliable and the pool is
extended, rather than published with a caveat (US1 scenario 3, SC-003).

⚠️ **`holes` is not a quality metric.** It says nothing about retrieval and
everything about the labels. Reading a low `holes` as a good result is the
category error the metric invites.

**The `*_passed` labels are recorded and not used to decide anything.** The
evaluator carries seven built-in thresholds (`ndcg_threshold=0.5`,
`fidelity_threshold=0.5`, `xdcg_threshold=50.0`, …) and promotes `ndcg@3` to a
top-level score. FR-010's «no pass threshold» is right about the judge and wrong
about the thresholds ([research.md § R8](../research.md)); the resolution is to
report the numbers and treat the labels as advisory.

### Two things the table must state in words

- **Whether the observed ordering matches what the source asserts** (SC-002).
  Learn says hybrid with semantic ranking wins «in benchmark testing» and
  publishes **no margin**. The margin measured here is a new fact, not a
  confirmation — and if the ordering does *not* hold on this corpus, that is a
  finding.
- **At least one case where the recall-shaped and ranking-shaped metrics
  disagree** (SC-004), or an explicit statement that none occurred. Learn's own
  worked example has `ndcg@3` 0.646 `pass` beside `fidelity` 0.019 `fail` — an
  excellent ranking over a result set that missed nearly everything. A single
  metric cannot see that.

### One worked example, in prose

A question where keyword retrieval fails and vector succeeds, or the reverse
(US1 scenario 4). The numbers say which method wins; one example says what each
method is *for*, which is the part that survives the exam.

---

## 5. What this measures, and what it does not

Stated in the write-up, not implied (FR-023):

- **Corpus**: this repository's own notes — small, homogeneous, single-author,
  and *about the technology being searched*. Documented as a **case study**, with
  what it buys (accurate labels, zero cost, full reproducibility) set against
  what it costs in external validity.
- **Labeller**: the author, who also wrote the corpus. No metric here detects
  that bias.
- **Scale**: ~145 chunks, ~20 questions. Nothing here is a benchmark result.
- **Ingestion**: local embedding and push, not integrated vectorization —
  documented as a case study too, including the two Free-tier reasons the
  alternative was unavailable.
