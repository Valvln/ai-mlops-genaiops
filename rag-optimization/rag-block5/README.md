# Block 5 — RAG retrieval quality, measured

AI-300 Domain 5. Blocks 3 and 4 asked whether a call, and then a judgement about
a call, could be retrieved after the fact. This block asks something upstream of
both: **how much does retrieval quality actually change across the four query
shapes, and by how much**.

## What this does

```bash
export AZURE_SEARCH_ENDPOINT="https://<service>.search.windows.net"
export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"

uv run chunk_corpus.py --report      # measure the corpus BEFORE cutting it
uv run chunk_corpus.py               # then cut: 222 chunks at 512/128
uv run create_index.py               # one index, 3072-dim HNSW, one semantic config
uv run embed_and_push.py             # the only step that spends: 0,0146 €
uv run service_stats.py --index      # what the Free tier really allows

uv run run_retrieval.py --method all # four query shapes, one embedding per question
uv run pool_for_labelling.py         # union of what they returned → the label set
uv run score_retrieval.py --all      # the comparison table
```

## The headline

| Method | ndcg@3 | fidelity |
| --- | ---: | ---: |
| `keyword` | 0.472 | 0.646 |
| `vector` | 0.579 | 0.816 |
| `hybrid` | 0.545 | 0.816 |
| **`hybrid_semantic`** | **0.601** | **0.843** |

`holes_ratio` 0.000 on all four. Full reading in
[results/retrieval-comparison.md](results/retrieval-comparison.md); the tier
measurements are in [results/free-tier-envelope.md](results/free-tier-envelope.md);
what building disproved is in
[../../specs/008-rag-retrieval-quality/findings.md](../../specs/008-rag-retrieval-quality/findings.md).

## 5 valuable findings

### 1. The documented ordering holds at the top and breaks in the middle

Learn says hybrid with semantic ranking wins «in benchmark testing» and publishes
no margin anywhere: the results confirm it. But plain `vector` beat `hybrid` on `ndcg@3`
(0.579 vs 0.545) and tied it on `fidelity`. So adding the BM25 leg and fusing
with RRF made the **ranking worse** than the vector query alone.

The margin is the part worth carrying into the exam: **+27 % over keyword, under
4 % over plain vector**. For small datasets, semantic re-ranking yields a smaller gain than moving from keyword to vector search.

### 2. No single number can capture the critical failure

q08 (*«Does a managed online endpoint keep billing when it receives no
traffic?»*) scored `fidelity` 0.89 and `ndcg@3` 0.143. Every method found the
relevant material and **none of them put it in the top three**. Reporting recall
alone calls that good retrieval; reporting ranking alone calls it a failure to
find anything. Both are wrong, and only the pair shows why.

### 3. Vector search succeeds, when it does, because of lexical matching

q14 asks how to record which prompt version produced a response. `vector` scored
0.904 and `keyword` 0.096. The chunk that answers it
talks about *git revisions attached to spans*; the question asks about *recording
a version*. BM25 matches terms, and the terms do not overlap. The embedding
places «which prompt produced this answer» near «resolves the prompt's git
revision» because they mean the same thing.

The inverse exists too: q19 asks which vector algorithm consumes vector quota,
and `keyword` (0.263) beat `vector` (0.165), because the answer is a table row
whose literal terms are the query's terms.

### 4. Retrieval has to run before labelling

The instinct is to decide what is relevant and then measure who found it. 
Adopting this approach causes every method to surface unevaluated documents. The 
`holes ratio` metric would measure label coverage instead of retrieval quality, 
creating a false impression of a healthy comparison.
Pooling — label the union of the methods' actually returned — is what got
`holes_ratio` to 0.000 on all four, while also inverting the pipeline's reading 
order.

### 5. What a green results table can hide

The first run of `score_retrieval.py` produced four methods, four ascending
numbers, and the expected ordering. It was wrong: the seven metrics are nested
under `document_retrieval_properties`, and the script was averaging the composite
at the top level. 

## Limits

The corpus has **only** 222 chunks, stating **homogeneous** format, register and 
structure. Its provenience is from a **single author**, so its vocabulary is more
consistent than a real-world one.

This corpus supports statements about this particular retrieval ladder: Nothing 
here constitutes proof of what might have been discovered regarding highly 
complex and heterogeneous documents.

### The label assignment method

378 (question, chunk) pairs, graded 0–3. **137 by hand (36 %)**, covering all 22
questions; the remaining **241 (64 %) by LLM**, calibrated against the manual
grades.

## What this cost

| | |
| --- | --- |
| Embedding the corpus, once | **0,0146 €** (73 249 tokens billed) |
| Query embeddings, 22 questions | 0,00006 € |
| Inference call under Foundry User | ~0,0002 € |
| Search service, Free tier | **0,00 €/day** |
| Foundry account + 2 deployments at rest | **0,00 €/day** |
| **Total** | **≈0,015 €** |

No fine-tuning artifact was created. No provisioned SKU was deployed. 
