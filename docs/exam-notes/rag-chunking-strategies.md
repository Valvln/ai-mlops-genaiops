# Chunking strategies for RAG — the numbers Microsoft actually publishes

**Status: documented, not measured.** Read from the Microsoft Learn pages under
*Sources* on **2026-08-27**, before the block 5 plan freezes.

Chunking is the step most often described in blog posts and least often
described with numbers. Learn publishes numbers, and they disagree with each
other in one place — § 2 is that disagreement, and it is the most useful thing
in this note.

---

## 1. Why chunk at all — two reasons, not one

The first reason is mechanical, and it is a hard limit:

> «Partitioning large documents into smaller chunks can help you stay under the
> maximum token input limits of chat completion and embedding models. For
> example, the maximum length of input text for the Azure OpenAI
> `text-embedding-3-small` model is **8,191 tokens**. Given that each token is
> around four characters of text for common OpenAI models, this maximum limit is
> equivalent to around **6,000 words** of text.»

The second reason is about quality, and it applies even when nothing overflows:

> «Chunking is only required if the source documents are too large for the
> maximum input size imposed by models, but it's **also beneficial if content is
> poorly represented as a single vector**. Consider a wiki page that covers
> numerous varied sub-topics. The entire page might be small enough to meet model
> input requirements, but you might get better results if you chunk at a finer
> grain.»

That second sentence is the exam-shaped one. A document that fits is not
therefore a good chunk: **one vector is one meaning**, and a page covering five
subjects averages them into a vector that is near none of them.

---

## 2. ⚠️ Two different recommended chunk sizes, on the same page

Learn gives a general recommendation:

> «We recommend starting with a chunk size of **512 tokens (approximately 2,000
> characters)** and an initial overlap of **25%, which equals 128 tokens**. This
> overlap ensures smoother transitions between chunks without excessive
> duplication.»

…and a technique-table recommendation that is materially smaller:

> «Define a fixed size that's sufficient for semantically meaningful paragraphs
> (for example, **200 words or 600 characters**) and allows for some overlap (for
> example, **10-15% of the content**).»

…and a Text Split skill default that matches the first:

| `textSplitMode` | `maximumPageLength` | `pageOverlapLength` |
| --- | --- | --- |
| `pages` | **2000** | **500** |

600 characters at 10–15% overlap and 2,000 characters at 25% overlap are not the
same strategy. Both appear in current documentation. **There is no single
"correct" chunk size to memorise**, and an exam answer asserting one is more
likely testing whether you know the trade-off than the constant.

The page then undercuts its own default with a worked example, which is the most
honest paragraph in it:

> «Although you could use the standard recommendation of 2,000 characters with a
> 500 character overlap, in this case it makes sense to go lower given the token
> counts of the sample document. In fact, **setting an overlap value that's too
> large can result in no overlap appearing at all**.»

For the NASA sample: 200 pages, average 189 tokens per page, maximum 1,583. Most
pages are *smaller* than the recommended chunk — so a 2,000-character window with
500 characters of overlap swallows whole pages and the overlap degenerates. The
lesson is procedural, not numeric: **measure the token distribution of the corpus
first, then choose the window.** `tiktoken` does it locally for free.

### Overlap, stated as a principle

> «The optimal overlap might vary depending on your content type and use case.
> For example, highly structured data might require less overlap, while
> conversational or narrative text might benefit from more.»

Structured content carries its own boundaries; prose does not, so prose pays for
continuity with duplication.

---

## 3. The five approaches

| Approach | What it is | Built-in support |
| --- | --- | --- |
| **Fixed-size** | a character or token window with overlap | Text Split skill, `pages` mode |
| **Variable-size by content** | split on sentence punctuation, line markers, or HTML/Markdown heading syntax | Text Split skill (`sentences`), Content Understanding skill |
| **Semantic chunking** | «break content into meaningful units that preserve context and semantic relationships across sentences and paragraphs»; can span page boundaries | Content Understanding skill (markdown output) |
| **Custom combinations** | e.g. variable-size chunks **plus the document title appended** to chunks from the middle of a document, «to prevent context loss» | **none** |
| **Document parsing** | an indexer parses one source document into several search documents — «strictly speaking, this approach isn't *chunking*» | one-to-many indexing, Markdown/JSON blob indexing |

The fourth row deserves attention because it has no built-in and is the one that
fixes the most common real defect: chunk 47 of a manual says "the limit is 30
days" and never says which policy. Prepending the document title, or the section
heading, is a two-line change with more effect on retrieval quality than most
parameter tuning.

The fifth row is a genuine distinction, not pedantry: one-to-many indexing
produces multiple *search documents* from one blob, which is what a chunked index
needs anyway — many rows, each with its own vector, all carrying a `parent_id`.

---

## 4. Text Split skill parameters

- `textSplitMode`: **`pages`** (default; chunks are multiple sentences) or
  `sentences` (single sentences, and «what constitutes a sentence is language
  dependent», controlled by `defaultLanguageCode`).
- `maximumPageLength` — maximum characters or tokens per chunk. *«The text
  splitter avoids breaking up sentences, so the actual character count depends on
  the content.»*
- `pageOverlapLength` — characters from the end of the previous page repeated at
  the start of the next. ⚠️ **«If set, this must be less than half the maximum
  page length.»** A hard validation rule, not advice.
- `maximumPagesToTake` — default `0`, meaning take all chunks.

⚠️ Characters are not tokens: *«The number of tokens measured by the LLM might be
different than the character size measured by the Text Split skill with the
character fixed-size.»* Token-mode chunking exists only in the
`2026-05-01-preview` skillset API.

### What the parameters do to chunk count

Learn's measurement on NASA's *Earth at Night* PDF (200 pages), which is the only
published before/after table on this subject:

| `textSplitMode` | `maximumPageLength` | `pageOverlapLength` | Chunks |
| --- | --- | --- | --- |
| `pages` | 1000 | 0 | 172 |
| `pages` | 1000 | 200 | **216** |
| `pages` | 2000 | 0 | 85 |
| `pages` | 2000 | 500 | **113** |
| `pages` | 5000 | 0 | 34 |
| `pages` | 5000 | 500 | 38 |
| `sentences` | — | — | **13,361** |

Three readings that matter for a 50 MB Free tier
(`rag-vector-store-and-indexing.md` § 5):

1. **Chunk count is vector count is quota.** Halving the window roughly doubles
   the chunks, and every chunk is one more embedding to pay for and one more
   vector to store. 1000/200 costs **2.5×** the vectors of 2000/500 on the same
   document.
2. **Overlap is not free.** At 1000 characters, adding 200 of overlap adds 26%
   more chunks; at 2000/500 it adds 33%. The duplication is paid twice — once at
   the embedding meter, once in the index.
3. **`sentences` mode is a different order of magnitude** — 13,361 chunks from
   200 pages, ~157× the `2000/500` configuration. It is not a tuning of `pages`;
   it is a different design, and on a small tier it is the one that exhausts the
   quota.

---

## 5. Choosing, in the order Learn suggests

> «Shape and density of your documents. If you need intact text or passages,
> larger chunks and variable chunking that preserves sentence structure can
> produce better results.»

> «User queries: Larger chunks and overlapping strategies help preserve context
> and semantic richness for queries that target specific information.»

> «Find a chunk size that works best for **all of the models you're using**. For
> instance, if you use models for summarization and embeddings, choose an optimal
> chunk size that works for both.»

The third is the constraint people discover late: the chunk is an input to the
embedding model *and* a fragment of the prompt sent to the chat model. A window
tuned only against the embedder can produce grounding context that is either too
thin to answer from or too fat to fit `k` of them in a prompt.

---

## 6. Where chunking sits in the workflow

Two places, and they are not symmetric:

- **Indexing** — chunk, embed, write one search document per chunk.
- **Query** — the query is *not* chunked; it is embedded whole.

Built-in path: integrated vectorization, where *«a default chunking strategy
using the Text Split skill is common»*. Custom path: a custom skill (Web API), or
chunking outside Search entirely and pushing the documents. Learn names
**LangChain Text Splitters** and **Semantic Kernel `TextChunker`** as external
libraries; the `RecursiveCharacterTextSplitter` example uses `chunk_size=1000,
chunk_overlap=200`, again below the stated default, for the reason in § 2.

For this repository the external path is not merely an alternative — on the Free
tier an indexer cannot authenticate outbound with a managed identity, and its
maximum run time with a skillset is 3–10 minutes. Chunking locally and pushing is
the option that keeps the credential posture and removes the timeout. See
`rag-vector-store-and-indexing.md` § 5.

---

## 7. What this note would cost to verify

**Chunking itself is free and local.** Splitting a corpus, counting tokens with
`tiktoken`, and comparing chunk counts across parameter sets costs nothing and
runs offline — it is the cheapest experiment in the whole block, and the one with
the most direct effect on every downstream cost.

What is *not* free is what follows each chunk:

| Step | Billed by | Note |
| --- | --- | --- |
| Splitting, token counting | — | local, free, repeatable |
| Embedding each chunk | Foundry, per token | scales linearly with chunk count — § 4 |
| Storing each vector | Search storage / vector quota | 0,00 € on Free, but capped at 50 MB |
| Re-chunking | Foundry again | **every parameter change re-embeds the whole corpus** |

That last row is the one to design around: a chunk-size sweep is not one
experiment, it is *n* full re-embeddings of the corpus. Keeping the corpus small
is what makes the sweep affordable, and a sweep over a small corpus still teaches
the shape of the trade-off. Figures in `rag-cost-model.md` § 3.

---

## Sources

- [Chunk documents for vector search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents) — read 2026-08-27; §§ 1–6, all quotations and both tables
- [Service limits for tiers and SKUs](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity) — read 2026-08-27; § 6, Free-tier indexer limits
- `rag-vector-store-and-indexing.md` §§ 5, 6 — where the chunks land and what they cost in quota
- `rag-retrieval-evaluation.md` — how to tell whether a chunking change helped
- `rag-cost-model.md` § 3 — the embedding rate behind § 7
