# Four retrieval methods, measured against labels

**User Story 1.** One index of 222 chunks, 22 questions (2 control), top 10,
labels 0–3 declared explicitly. `DocumentRetrievalEvaluator` from
`azure-ai-evaluation 1.18.3` — arithmetic over labels, no judge model, no model
call.

| Method | ndcg@3 | fidelity | xdcg@3 | top1_rel | top3_max_rel | holes | holes_ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `keyword` | 0.472 | 0.646 | 32.07 | 1.64 | 2.18 | 0 | 0.000 |
| `vector` | 0.579 | 0.816 | 39.40 | 1.82 | 2.36 | 0 | 0.000 |
| `hybrid` | 0.545 | 0.816 | 37.31 | 1.68 | 2.32 | 0 | 0.000 |
| **`hybrid_semantic`** | **0.601** | **0.843** | **39.87** | 1.77 | 2.32 | 0 | 0.000 |

**`holes_ratio` is 0.000 on every method**, which is what makes the rest of the
table readable. It is not a quality result — it says the pool was built from what
the methods actually returned, so no method was scored against documents nobody
judged. Pooling before labelling is what bought that, and it is the reason
retrieval had to run before the ground truth existed.

The `*_passed` labels are recorded and decide nothing (FR-010). For the record,
the evaluator's own thresholds would fail `ndcg@3` on three of four methods and
`xdcg@3` on all four, against defaults calibrated for datasets of 50+ documents.

---

## 1. The ordering matches the source, and the margin is small

Learn asserts that hybrid retrieval with semantic ranking wins «in benchmark
testing» and **publishes no margin anywhere** — neither on the hybrid overview
nor on the ranking page. Measured here:

```text
hybrid_semantic  0.601   >   vector  0.579   >   hybrid  0.545   >   keyword  0.472
```

**The ordering holds at the top and breaks in the middle.** `hybrid_semantic` is
first, as asserted. But plain `vector` beats `hybrid` on `ndcg@3` (0.579 vs
0.545) and ties it on `fidelity` (0.816) — so RRF fusion made ranking *worse*
than the vector leg alone on this corpus. That is a partial contradiction of the
usual framing, in which hybrid is presented as dominating both of its legs.

**The margin is the new fact.** `hybrid_semantic` over `keyword` is **+0.129
ndcg@3, a 27 % relative improvement**; over `vector`, the next best, it is
**+0.022, under 4 %**. On a corpus of this size and homogeneity, the entire
semantic-ranking stage buys less than the difference between keyword and vector
search does. A reader deciding whether to enable semantic ranking on a small
corpus now has a number where the documentation offers an adjective.

⚠️ 22 questions on 222 chunks from one author. This is a measurement, not a
benchmark, and § 4 says what it cannot support.

---

## 2. Where the two metric shapes disagree (SC-004)

`ndcg@3` is ranking-shaped: it asks whether the best documents are at the top.
`fidelity` is recall-shaped: it asks how much of the known-good set was found at
all. They come apart repeatedly here, and in both directions.

**q08 — «Does a managed online endpoint keep billing when it receives no
traffic?»**

| | keyword | vector | hybrid | hybrid_semantic |
| --- | ---: | ---: | ---: | ---: |
| `ndcg@3` | 0.160 | 0.143 | 0.143 | **0.076** |
| `fidelity` | 0.48 | **0.89** | **0.89** | 0.67 |

Every method found most of the relevant material — `fidelity` 0.89 for vector and
hybrid — and **no method put any of it in the top three**. `ndcg@3` of 0.076 for
`hybrid_semantic` beside a `fidelity` of 0.67 is the clearest case in the set: the
answer was retrieved and buried. Reporting recall alone would call this retrieval
good; reporting ranking alone would call it a failure to find anything. Both
readings are wrong, and only the pair shows why.

**q19 — the reverse.** `hybrid_semantic` scores `ndcg@3` 0.923 with `fidelity`
1.00, while `vector` scores 0.165 with 0.67: here the semantic reranker both found
more and ordered it correctly, and the two metrics agree. The contrast with q08 is
the point — a single metric cannot tell the two situations apart.

**q14 and q17** show the same split more mildly: `keyword` reaches `ndcg@3` 0.096
and 0.227 against `fidelity` 0.29 and 0.65, so BM25 found some of the right
material and ranked almost none of it well.

---

## 3. One worked example, in prose

**q14 — «How do I record which version of a prompt produced a given response?»**

| Method | ndcg@3 | What came back at rank 1 |
| --- | ---: | --- |
| `keyword` | **0.096** | `network-isolation.md` § 7, a price table |
| `vector` | **0.904** | `prompt-and-agent-versioning.md`, the preamble |

The corpus contains a near-perfect answer: the preamble of
`prompt-and-agent-versioning.md` states that `call_model.py` resolves the prompt
file's git revision before each call and attaches it to the span — which is
literally the question, answered by this repository's own code.

**Keyword search missed it and vector search found it, and the reason is lexical.**
The question asks about *recording a version*; the chunk that answers it talks
about *git revisions attached to spans*. BM25 matches terms, and the terms do not
overlap: «record» does not appear, «version» appears in a dozen chunks about model
versions and API versions, and the strongest lexical signal in the query —
«response» — pulls toward chunks about HTTP responses and endpoint scoring. The
embedding does not care about the words; it places «which prompt produced this
answer» near «resolves the prompt's git revision and attaches it to the trace»
because they mean the same thing.

This is what the numbers cannot say on their own. `vector` wins the column, but
the reason it wins — that the corpus answers the question in different words than
the question uses — is the property that decides when to reach for vector search
and when BM25 will do. The inverse case exists too: **q19** asks «which vector
search algorithm consumes vector quota», and `keyword` (0.263) beats `vector`
(0.165), because the answer is a table row whose literal terms are the query's
terms.

---

## 4. Ground truth, and what it is not

**The label set is mixed in provenance.** 378 (question, chunk) pairs were graded
0–3: **137 by hand (36 %)** across all 22 questions, and the remaining
**241 (64 %) by Claude**, calibrated against the manual grades. The manual pass
covered every question, so each one carries a human reference for how the scale
was applied; no question was graded entirely without one.

Other limits, stated rather than implied:

- **Corpus**: this repository's own notes — small, homogeneous, single-author, and
  *about the technology being searched*. A case study, not a sample.
- **Labeller bias**: the human half was graded by the corpus's own author. No
  metric here detects that.
- **Scale**: 222 chunks, 22 questions. The evaluator's own thresholds assume
  50+ documents, which is why they are recorded and not used.
- **q21 is a compromised control.** It asks which models support the Batch API and
  what discount batch applies. The corpus does not name the Batch API — which is
  what was verified when the question was written — but
  `foundry-deployment-types.md` § 5 *does* state the 50 % batch discount, so one
  chunk is genuinely relevant and is graded 2. Half the question is answerable,
  and q21 therefore does not test what a control is supposed to test.
- **q22 is a clean control**: 18 pooled chunks, all graded 0, `ndcg@3` 0.000 on all
  four methods. No method surfaced an answer that does not exist.
