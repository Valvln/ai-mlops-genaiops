# The Free tier's real envelope, read off the service

**User Story 2.** Measured 2026-08-27/28 against `ai300srch…` in `swedencentral`,
free tier, `semanticSearch: 'free'`. Raw responses in
`specs/008-rag-retrieval-quality/evidence/`.

Everything below is a number the service returned. Nothing here is inferred from
the pricing page.

---

## 1. What `/servicestats` reports on an empty service

```text
GET https://<service>.search.windows.net/servicestats?api-version=2025-09-01
```

| Counter | Quota returned | Published figure | Verdict |
| --- | ---: | ---: | --- |
| `storageSize` | **52 428 800** | 50 MB | confirms |
| `indexesCount` | 3 | 3 | confirms |
| `indexersCount` | 3 | 3 | confirms |
| `dataSourcesCount` | 3 | 3 | confirms |
| `skillsetCount` | 3 | 3 | confirms |
| `synonymMaps` | 3 | 3 | confirms |
| `documentCount` | **`null`** | 10 000 per indexer invocation | not comparable — see below |
| **`vectorIndexSize`** | **`null`** | ⚠️ **nothing** — no Free column exists | **contradicts the expectation** |

`limits` alongside them: `maxStoragePerIndex` 52 428 800, `maxFieldsPerIndex`
1 000, `maxFieldNestingDepthPerIndex` 10, `maxComplexCollectionFieldsPerIndex`
40, `maxComplexObjectsInCollectionsPerDocument` 3 000. The field limit confirms
the note's row that Basic — not Free — is the tier with the *lower* 100-field cap.

### The number nobody publishes, the service does not publish either

`rag-vector-store-and-indexing.md` § 4 flagged that the vector-quota table has
columns for Basic through L2 and **no Free column**, and proposed reading the
value off `/servicestats` instead. That was the whole of SC-005.

**The endpoint returns `null`.** Not zero, not a number: the field is present and
carries no quota. So the Free tier does not expose a vector-index quota through
either channel.

This is a result, not a failed measurement, and it settles the open question in
the note's favour by elimination rather than by confirmation: **there is no
separate vector budget at this tier, and the 50 MB service storage limit is the
only declared ceiling.** The note's «plausible reading … but that is inference,
not a documented figure» can now say *inference confirmed by the absence of any
competing limit* — which is weaker than a published number and is what is
actually available.

`documentCount.quota` is `null` for the same structural reason. The published
10 000 is a per-**indexer-invocation** limit, and this feature runs no indexer;
nothing caps documents on a free service except storage.

---

## 2. After ingestion — 222 documents

```text
GET .../indexes/exam-notes/stats?api-version=2025-09-01
```

| | Measured | Predicted | |
| --- | ---: | ---: | --- |
| `documentCount` | 222 | 222 | — |
| `storageSize` | 8 832 585 B (8,42 MB) | — | 16,8 % of the 50 MB quota |
| **`vectorIndexSize`** | **8 222 516 B (7,84 MB)** | 2 727 936 B (2,60 MB) | **3,01× the formula** |

The prediction is the documented formula: 222 documents × 3072 dimensions ×
4 bytes per `float32`. The measurement is three times larger — **37 038 bytes per
document** where the raw vector is 12 288.

⚠️ **The gap is not reconciled away, and it is not an error.** The formula prices
the vectors; the service also stores the HNSW graph that makes them searchable,
and that structure is not in the arithmetic. Whatever its exact composition, the
operative fact for sizing is that **the documented formula underestimates a
3072-dimension HNSW field by a factor of three at this scale.**

**What that means for the tier.** At 39 786 bytes of total storage per document,
the 50 MB limit binds at roughly **1 300 chunks** of this shape — not the ~4 200
the formula alone would suggest. A corpus three times this one still fits; ten
times does not. Anyone sizing a Free-tier vector index from the formula would
discover this at the point of refusal.

**A cheaper lever exists and was deliberately not pulled**: compression and
quantization would cut the vector footprint substantially. Measuring them is out
of scope, and configuring an unmeasured one would have made this number a
property of the configuration rather than of the tier.

⚠️ **Index statistics lag.** Immediately after a successful push the endpoint
still reported `documentCount: 0` while a direct query counted 222. The stats
endpoint is not a source of truth about *whether* ingestion succeeded — only
about how much room it took, and only once it catches up.

---

## 3. Chunking — which recommendation was followed, and which was not

Measured before cutting, per FR-002:

| | |
| --- | --- |
| Corpus | 18 notes, `docs/exam-notes/*.md` @ `802a57f` |
| Tokens (`o200k_base`) | **65 688**, mean 3 649 per note |
| Sections split on H2 | 177, of which **38 exceeded the cap** and were windowed |
| Chunks | **222** — min 76, median 316, max 512 tokens |
| Tokens embedded | 72 711 predicted, **73 249 billed** (1,11× the corpus, from overlap) |

`rag-chunking-strategies.md` § 2 records that Learn publishes **two mutually
inconsistent recommendations on the same page**: 512 tokens with 25 % overlap,
and 200 words / 600 characters with 10–15 % overlap.

**The first was followed** — 512 tokens, 128 overlap — and the second was not.
The reason is the corpus measurement above, not preference: at a mean of 3 649
tokens per note and a median section well under the cap, a 200-word window would
have cut most sections into three or four pieces each, tripling the chunk count
to no purpose on documents whose H2 sections are already coherent units.

**The inconsistency is not resolved by this feature.** Resolving it needs a
chunk-size sweep, which re-embeds the whole corpus once per cell — the expensive
axis, where varying the retrieval method is the cheap one. It is out of scope by
decision and recorded as such, not left unsaid.

⚠️ Note also that the plan's own estimate was wrong: `data-model.md` § 2 predicted
~55 000 tokens and ~145 chunks. Measured, 65 688 and 222. The measurement replaces
the estimate — which is the entire reason FR-002 puts measuring before cutting.

The tokenizer disagrees with the service too, mildly: `tiktoken` counted 72 711
where the service billed **73 249**, a 0,74 % underestimate. Small, one-directional,
and worth knowing before a local count is used to predict a bill.

---

## 4. Ingestion path — push, and why the tutorials' path was unavailable

Documents are chunked and embedded **locally** and pushed over the data plane
with an Entra ID token. The path Learn's tutorials take — an indexer with
integrated vectorization — was rejected for two independent Free-tier reasons:

1. **No managed identity for indexer outbound connections on Free.** The indexer
   would need a key-bearing connection string to reach its data source and its
   embedding skill, reintroducing exactly the credential that `disableLocalAuth`
   removes from both services.
2. **Runtime and enrichment caps**: 1–3 minutes per run (3–10 with a skillset),
   and 20 AI-enrichment transactions per indexer per day.

Reason 1 decided it; reason 2 would merely have been inconvenient. FR-003's
downgrade clause — permission to accept a key if the credential-less path proved
impossible — therefore **stayed dormant**: the posture was preserved, not traded.

The mechanism not used is documented beside the one that was, because knowing
*why* integrated vectorization is unavailable here is the examinable half.

---

## 5. Refusals — the only direct measurement of a boundary

One refusal was produced, and it is more interesting than a quota rejection.

**Keys still exist on a service with `disableLocalAuth: true`, and they are
readable.**

```text
az search admin-key show --service-name <service> -g rg-ai300-rag
  { "primaryKey": "…", "secondaryKey": "…" }        # HTTP 200, keys returned
```

**And they do not work.**

```text
curl -H "api-key: <primaryKey>" ".../indexes/exam-notes/docs/$count?api-version=2025-09-01"
  HTTP 401
```

⚠️ **`disableLocalAuth` disables key *authentication*, not key *existence*.** The
secret material is still provisioned, still rotatable, and still readable by
anyone holding a control-plane role that grants `listAdminKeys` — Owner or
Contributor. What the flag removes is the data plane's willingness to accept it.

The practical consequence: "there are no keys in this feature" is a true statement
about how anything authenticates, and a false one about what exists. Flip the flag
and those two strings work immediately. On a disposable learning service that is
a curiosity; on a production service it is the difference between a credential
that cannot be used and a credential that has been deleted, and only the second is
a security property.

Related, and by design rather than by discovery: `authOptions` reads back `null`.
The two properties are mutually exclusive, so the template omits `authOptions`
entirely rather than setting it to an RBAC-flavoured value — a template setting
both does not deploy.

**No tier refusal occurred.** Nothing in this phase hit the 3-index limit, the
50 MB storage limit, or the semantic-query allowance. Stated explicitly rather
than left as an empty section: the boundaries were read, not struck.
