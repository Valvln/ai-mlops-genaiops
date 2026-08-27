# Evaluating retrieval quality — process evaluation, and the metrics that need labels

**Status: documented, not measured.** Read from the Microsoft Learn page under
*Sources* on **2026-08-27**, before the block 5 plan freezes.

Block 4 evaluated **responses** — groundedness and relevance on a generated
answer. This note is about the step upstream: evaluating the **retrieval**, on
its own, before any model writes a sentence. Foundry treats these as two
categories with different names, and knowing which is which is most of the
exam-shaped content.

---

## 1. Process evaluation vs system evaluation

| | Evaluates | Evaluators |
| --- | --- | --- |
| **Process evaluation** | the **document retrieval step** | Retrieval, Document Retrieval |
| **System evaluation** | the **final response** | Groundedness, Groundedness Pro, Relevance, Response Completeness |

The reason for splitting them:

> «Because of its upstream role in RAG, the retrieval quality is important. **If
> the retrieval quality is poor and the response requires corpus-specific
> knowledge, there's less chance your language model gives you a satisfactory
> answer.**»

A low groundedness score has two possible causes — the model fabricated, or the
retrieval never supplied the fact. **System evaluation alone cannot tell them
apart.** Block 4 measured only the response half; this is the missing half, and
the distinction is the answer to "which knob do I turn".

---

## 2. The six evaluators

| Evaluator | Best practice | Use when | Measures | Output |
| --- | --- | --- | --- | --- |
| **Document Retrieval** | process | retrieval is the bottleneck **and you have query relevance labels** | search-quality metrics vs ground-truth labels | composite: Fidelity, NDCG, XDCG, Max Relevance, Holes |
| **Retrieval** | process | you want textual quality of retrieved context **but have no ground truth** | how relevant the retrieved chunks are, **via an LLM judge** | Pass/Fail on a 1–5 scale |
| **Groundedness** | system | you want a well-rounded definition, bring your own GPT judge | response aligns with context without fabricating — **precision** | Pass/Fail on a 1–5 scale |
| **Groundedness Pro** (preview) | system | you want a strict definition, Microsoft's service model | strict consistency, via Azure AI Content Safety | **True/False** |
| **Relevance** | system | no ground truth | accuracy, completeness and direct relevance of response to query | Pass/Fail on a 1–5 scale |
| **Response Completeness** (preview) | system | you must not miss critical information | coverage vs ground truth — **recall** | Pass/Fail on a 1–5 scale |

The precision/recall pairing is stated explicitly and is the cleanest way to hold
the two apart:

> «**Groundedness** focuses on the *precision* aspect of the response. It doesn't
> contain content outside of the grounding context. **Response completeness**
> focuses on the *recall* aspect. It doesn't miss critical information compared to
> the expected response or ground truth.»

### Required inputs — the table that decides what a test set must contain

| Evaluator | Required inputs | Required parameters |
| --- | --- | --- |
| Groundedness | `response`, `context` (optional but recommended), `query` optional | `deployment_name` |
| Groundedness Pro | `query`, `response`, `context` | *(none)* |
| Relevance | `query`, `response` | `deployment_name` |
| Response Completeness | `ground_truth`, `response` | `deployment_name` |
| **Retrieval** | **`query`, `context`** | `deployment_name` |
| **Document Retrieval** | **`retrieval_ground_truth`, `retrieved_documents`** | ***(none)*** |

⚠️ **Read the last two rows against each other.** `Retrieval` needs no labels but
needs a model deployment — it is an LLM judge, and it is billed per token like
any other call. `Document Retrieval` needs no model at all — it is arithmetic
over labels — but it needs a human-labelled ground truth that does not exist
until someone writes it.

So the cost of the two is inverted: one costs tokens and no labour, the other
costs labour and no tokens. On a small corpus, `Document Retrieval` is the
**cheaper** of the two to run and the more expensive to prepare — and it is the
only one that yields metrics precise enough to tune parameters against.

`context` is a plain string; multi-chunk retrieval is concatenated with a
separator such as `\n\n`.

---

## 3. Document Retrieval's five metrics

| Metric | Category | What it measures |
| --- | --- | --- |
| **Fidelity** | Search Fidelity | «How well the top n retrieved chunks reflect the content for a given query: number of good documents returned **out of the total number of known good documents** in a dataset» |
| **NDCG** | Search NDCG | «How good are the rankings **to an ideal order** where all relevant items are at the top of the list» |
| **XDCG** | Search XDCG | «How good the results are in the **top-k** documents regardless of scoring of other index documents» |
| **Max Relevance N** | Search Max Relevance | «Maximum relevance in the top-k chunks» |
| **Holes** | **Search Label Sanity** | «Number of documents with **missing query relevance judgments**, or ground truth» |

Fidelity is recall-shaped: did the good documents come back at all. NDCG and
XDCG are order-shaped: did they come back near the top. They answer different
questions and can move in opposite directions — a change that retrieves one more
relevant document but pushes it to position 9 improves fidelity and worsens NDCG.

**Holes is not a quality metric.** Its category is *Label Sanity*: it counts
retrieved documents the ground truth says nothing about. A high `holes_ratio`
means the labels are incomplete, so **the other four metrics are unreliable** —
documents may be scored as misses simply because nobody judged them. Learn's own
sample output shows exactly this failure mode:

```python
{ "metric": "ndcg@3",   "score": 0.646, "label": "pass", "passed": true  },
{ "metric": "fidelity", "score": 0.019, "label": "fail", "passed": false }
```

NDCG@3 passes at 0.646 while fidelity fails at 0.019. A ranking can be excellent
over a result set that missed almost everything worth finding. **Reporting only
NDCG would call this retrieval good.** That is the same defect this repository
keeps meeting — a check that passes while the objective is missed — arriving here
in metric form. The output also returns `xdcg@3`, `top1_relevance`,
`top3_max_relevance`, `holes` and `holes_ratio`.

### The labels

```python
retrieval_ground_truth = [
    {"document_id": "1", "query_relevance_label": 4},
    {"document_id": "2", "query_relevance_label": 2},
]
retrieved_documents = [
    {"document_id": "2", "relevance_score": 45.1},
    {"document_id": "6", "relevance_score": 35.8},
]
```

Graded relevance, not binary. Configured by
`ground_truth_label_min` / `ground_truth_label_max` — **SDK defaults 0 and 4**,
while Learn's own example passes 1 and 5. Mismatching the declared range against
the labels rescales every metric silently.

Note `document_6` in the retrieved list: not in the ground truth, therefore a
hole. The example is built to produce one.

---

## 4. Parameter sweep — the reason this note exists

> «To optimize your RAG in a scenario called **parameter sweep**, you can use
> these metrics to calibrate the search parameters for the optimal RAG results.
> Generate different retrieval results for various search parameters such as
> **search algorithms (vector, semantic), `top_k`, and chunk sizes** you're
> interested in testing. Then use `document_retrieval` to find the search
> parameters that yield the highest retrieval quality.»

This is the missing link between the previous three notes and a result. Chunk
size (`rag-chunking-strategies.md` § 4), retrieval method
(`rag-hybrid-search-and-ranking.md` § 1) and `k` are all parameters whose effect
Learn describes qualitatively and never quantifies. A sweep scored by
`document_retrieval` converts them into a table.

⚠️ **The sweep is not free even though the evaluator is.** Each cell costs:

| Cost | When |
| --- | --- |
| re-embedding the corpus | only when the **chunk size** changes |
| one query embedding per question | every cell |
| semantic ranker queries | only for the semantic cells, against the free allowance |
| `document_retrieval` itself | **nothing — no `deployment_name`** |
| labelling | once, up front, in human time |

A sweep varying *only* method and `k` re-uses one embedded corpus and costs a
handful of query embeddings. A sweep varying chunk size multiplies the corpus
embedding cost by the number of chunk sizes. **The cheap axis and the expensive
axis are not the same axis**, and a spec with eight days should say which one it
sweeps.

---

## 5. Scores, thresholds, and the block 4 scar

The LLM-judge evaluators return 1–5, **default pass threshold 3**, and emit a
`reason`:

```json
{ "name": "Groundedness", "metric": "groundedness", "score": 4,
  "label": "pass", "reason": "…", "threshold": 3, "passed": true }
```

Block 4 already measured what this default does: finding F5 recorded that the
default threshold **promoted a confident fabrication**, because the judge scores
how the claim is *asserted*, not whether it is *true*. Nothing in the current
documentation contradicts that measurement — Learn documents the threshold's
value, not its adequacy.

The two facts sit together cleanly, which is what the amended constitution is
after: the **source** says the default is 3; the **measurement** says 3 admitted
a fabrication on this corpus. Neither is wrong. Recorded together, the pair is
worth more than either alone, and it is the reason `document_retrieval` — which
has no judge and no threshold — is the better instrument for tuning.

---

## 6. What this note would cost to verify

| Step | Cost |
| --- | --- |
| Writing a labelled question set (~20 questions) | **0,00 €** — human time, local, interruptible |
| Running `document_retrieval` | **0,00 €** — no model deployment required |
| Running `Retrieval` / `Groundedness` / `Relevance` | Foundry tokens for the judge model |
| Retrieval calls themselves | 0,00 € on the Free search tier |
| Re-embedding for a chunk-size axis | Foundry tokens × corpus × number of sizes |

The labelled question set is the asset with the longest life here: it is local,
free, version-controllable, costs nothing to keep, and every future comparison
re-uses it. It is also the only thing on this list that cannot be regenerated by
running a command — which argues for writing it before the environment exists,
not after.

⚠️ Block 4 left **finding F6 open**: evaluation spans were accepted and then did
not appear in the trace store, and the token counter reported 3 of ~13 calls
because it reads from that store. Any evaluation result in block 5 that is read
back *through tracing* inherits that defect. Reading evaluator output directly
from the SDK return value does not. Choose the direct path, and say so.

---

## Sources

- [RAG evaluators for generative AI (Microsoft Foundry)](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/evaluation-evaluators/rag-evaluators) — read 2026-08-27; all sections, every quotation and table
- `qa-observability/foundry-block4/` and its `findings.md` — F5 (threshold promotes a confident fabrication) and F6 (spans accepted then absent)
- `genai-tracing.md` — how evaluation results reached the trace store in block 4
- `rag-chunking-strategies.md` § 4, `rag-hybrid-search-and-ranking.md` § 1 — the parameters § 4 sweeps
- `rag-cost-model.md` § 3 — the embedding and judge-model rates
