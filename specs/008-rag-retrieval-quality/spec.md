# Feature Specification: Block 5 — RAG Retrieval Quality, Measured

**Feature Branch**: `008-rag-retrieval-quality`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "Block 5 — RAG optimization and fine-tuning (AI-300
Domain 5, 10-15%). The last block. Build one working RAG pipeline on Azure AI
Search's Free tier and measure how retrieval quality changes across retrieval
methods, scored by a labelled ground-truth set rather than by opinion. Free tier
or nothing; fine-tuning priced and closed as theory; two `foundry.bicep` debts
settled; about 8 days."

## Context

This is the fifth and last block, opening AI-300 Domain 5 — the only domain with
zero coverage in this repository. It is also the first feature written under
constitution **1.1.0**, whose new Development Workflow rule requires that the
research phase produce sourced notes in `docs/exam-notes/` **before the plan
freezes**.

### The research phase is complete, and is a precondition rather than a task

Six notes were written on **2026-08-27** from current Microsoft Learn pages, each
listing its sources and reading date:

| Note | Covers |
| --- | --- |
| `rag-vector-store-and-indexing.md` | vector fields, HNSW vs exhaustive KNN, quota accounting, quantization, the Free tier's published limits |
| `rag-chunking-strategies.md` | chunk size and overlap, the Text Split skill, the chunk-count table |
| `rag-hybrid-search-and-ranking.md` | BM25, RRF, the semantic reranker, three score ranges |
| `rag-retrieval-evaluation.md` | process vs system evaluation, the Document Retrieval metrics |
| `fine-tuning-vs-rag.md` | the prompt → RAG → fine-tuning ladder, SFT/DPO/RFT |
| `rag-cost-model.md` | every rate quoted in this spec |

**This feature does not re-derive, restate or rewrite them.** They are cited.
What they could not supply — because Learn does not publish it — is what this
feature measures.

### Why this feature exists: two gaps the source leaves open

1. **Learn publishes no vector-index quota for the Free tier.** The quota table
   in the service-limits article has columns for Basic through L2 and no Free
   column, while a separate page states vector search runs «on all tiers at no
   extra charge». The 50 MB service storage limit is the plausible binding
   constraint, but that is inference. One unauthenticated data-plane call returns
   the real number.
2. **Learn asserts that hybrid retrieval with semantic ranking ranks best, and
   publishes no margin.** Both the hybrid overview and the ranking page state the
   ordering — «in benchmark testing, this combination consistently produced the
   most relevant results» — with no NDCG table attached. The margin on a real
   corpus is this feature's principal deliverable.

Both are exactly the case the amended constitution anticipates: the measurement
does not contradict the source, it supplies what the source omits.

### What block 4 left, and what this feature must not inherit

Block 4 (feature 007) measured the **response**: groundedness and relevance on a
generated answer. It also left finding **F6 open** — evaluation spans were
accepted and then did not appear in the trace store, and the token counter, which
reads from that store, reported 3 of ~13 calls. Any result read back *through
tracing* inherits that defect. This feature reads evaluator output directly from
the return value instead, and says so (FR-014).

Block 4 also recorded finding **F5**: the default LLM-judge threshold promoted a
confident fabrication. This feature's core measurement therefore uses the
**Document Retrieval** evaluator, which has no judge and no threshold — it is
arithmetic over human labels — rather than an LLM-scored proxy.

### The environment does not exist

`rg-ai300-foundry` was torn down at block 3's close and nothing exists in this
subscription today: zero resource groups, zero spend. Delivering this feature
requires redeploying `infra/foundry.bicep` from an empty resource group, and that
redeployment is itself evidence (see User Story 3).

⚠️ **The Foundry account name from block 3 is soft-deleted for 48 hours** from
its teardown, and purging is irreversible. The decision recorded on 2026-08-22
was **not to purge**. If the window has not expired, this feature deploys into a
resource group whose name has not been used before, rather than purging.

### Non-negotiable constraints, decided before this spec and not reopened here

1. **Azure AI Search Free tier, or no search service at all.** Basic is
   **0,0887 €/hour = 2,13 €/day** and does not stop. If the Free tier turns out
   to be insufficient for something this spec wants to demonstrate, **the spec is
   reduced — the tier is never raised.**
2. **Fine-tuning is priced and not executed.** Hosting a fine-tuned deployment is
   **1,4937 €/hour = 35,85 €/day**, flat across `gpt-4.1-nano`, `gpt-4.1-mini`
   and `gpt-4.1`, and fine-tuned inference is billed at the base model's own
   token rate. Training is cheap (4,40–5,80 € per million tokens); **hosting is
   what makes it impossible.** Closed as theory on exactly the grounds provisioned
   throughput was closed in block 3.
3. **Nothing that bills at rest is created before its daily rate and deletion
   command are written into the Cost section below.**
4. **Region `swedencentral` for Foundry**, as block 3 established: `northeurope`
   offers chat models only as provisioned. Not re-derived here.
5. **Per-token model deployments only.** Never provisioned, at any stage.
6. **No hub.** Excluded by construction, as in blocks 3 and 4.
7. **The environment is disposable.** Teardown is a success criterion (SC-009),
   not a closing note.

### Calendar

About **8 days**, then two weeks of total absence. The scope below is already
cut: the chunk-size sweep is **out** (see Out of Scope), because varying chunk
size re-embeds the whole corpus and multiplies the only line item that costs real
money, while varying retrieval method re-uses one embedded corpus. One closed
story is worth more than three open ones.

---

## User Scenarios & Testing *(mandatory)*

**Sequencing note**: the stories are prioritised by value, not by order of
execution. US3's redeployment produces the model deployments US1 and US2 consume,
so it runs first in wall-clock time while being the least valuable of the three
if only one could ship.

### User Story 1 - The retrieval ladder, measured against labels (Priority: P1)

A learner wants to know, on a corpus they understand well, how much retrieval
quality actually changes as they move from keyword search to vector search to
hybrid to hybrid with semantic ranking — and to know it as a number produced by a
labelled ground truth, not as an impression formed by reading a few result lists.

**Why this priority**: this is Domain 5's core content and the deliverable the
source cannot supply. It is also the story that converts four separate documented
mechanisms into one comparison a reader can check.

**Independent Test**: with a search index populated and a labelled question set
in place, run the four retrieval shapes and produce a scored table. Delivers the
margin Learn omits, and can be demonstrated without any of US2's quota work.

**Acceptance Scenarios**:

1. **Given** a corpus indexed with both text and vector fields, **When** the same
   question set is run through keyword-only, vector-only, hybrid, and hybrid with
   semantic ranking, **Then** each method produces its own retrieval-quality
   scores over the same labelled ground truth, and the four are directly
   comparable.
2. **Given** the scored results, **When** the best-performing method is
   identified, **Then** it is identified **by the numbers**, and the record states
   whether the observed ordering matches, or fails to match, what the source
   asserts.
3. **Given** the label-sanity metric reports a high proportion of retrieved
   documents with no relevance judgment, **Then** the comparison is treated as
   unreliable and the label set is extended before any conclusion is drawn.
4. **Given** a question whose answer exists in the corpus, **When** keyword search
   fails to retrieve it and vector search succeeds (or the reverse), **Then** that
   case is recorded as a worked example of what each method is for.
5. **Given** a retrieval method is changed, **When** the corpus embeddings are
   unchanged, **Then** no re-embedding cost is incurred.

---

### User Story 2 - The Free tier's real envelope (Priority: P2)

A learner wants to know what the free search service actually permits, rather
than what the documentation happens to publish — how much vector index it will
hold, how much of that a real corpus consumes, and which of the repository's
established practices the tier forbids.

**Why this priority**: it produces the fact the source omits, it costs nothing,
and it is the story most likely to survive if time runs short — it needs one
index and no labelled question set.

**Independent Test**: create the free service, index the corpus, and read the
service's own statistics. Delivers a measured quota figure and a measured index
size with no evaluation apparatus at all.

**Acceptance Scenarios**:

1. **Given** a free search service exists, **When** its service statistics are
   read, **Then** the storage quota and the vector index quota are recorded as
   numbers, and the record states whether they confirm or contradict the inference
   that the 50 MB service storage limit binds first.
2. **Given** the corpus is indexed, **When** the index statistics are read,
   **Then** the actual vector index size is recorded and compared against the
   size predicted by the documented formula.
3. **Given** the tier forbids managed identity for indexer outbound connections,
   **When** the ingestion path is chosen, **Then** the choice and its reason are
   recorded, and the repository's credential-less posture is either preserved or
   its downgrade is documented as forced by the tier.
4. **Given** an attempt is made that the tier does not permit, **Then** the
   refusal is captured verbatim, because the refusal is the evidence.

---

### User Story 3 - Two debts on `foundry.bicep`, settled (Priority: P3)

The template still grants an inference role that current documentation explicitly
advises against, and the template's hard-won ability to run twice in a row has not
been exercised since block 4 fixed it. This feature redeploys the template
anyway, so both are settled at no extra cost.

**Why this priority**: high value per unit of effort and low risk, but it settles
debts rather than opening the domain. If the block collapses to one story, this
is not the one to keep — though in practice it runs first.

**Independent Test**: deploy the template twice into an empty resource group and
make one inference call. Requires no search service and no corpus.

**Acceptance Scenarios**:

1. **Given** the template grants the inference role by role-definition identifier
   rather than by display name, **When** it is deployed and an inference call is
   made with no Cognitive Services role assigned anywhere, **Then** the call
   succeeds — and that line becomes the only one in the repository that is both
   measured and prescribed.
2. **Given** the call does **not** succeed under the prescribed role, **Then** the
   divergence is written up as a finding naming which of source and measurement is
   wrong and on what evidence, and the older grant is restored with that finding
   cited beside it.
3. **Given** the template has been deployed once successfully, **When** it is
   deployed again immediately with no manual intervention and no portal fix,
   **Then** the second deployment also succeeds.
4. **Given** the template deploys an embedding model as well as a chat model,
   **When** both deployments report success, **Then** both are per-token and
   neither is provisioned.

---

### Edge Cases

- **Semantic ranking is unavailable in the chosen region.** It is offered in
  select regions only, and the Free tier permits **one service per subscription**
  — so a region chosen wrongly must be deleted and recreated. Regional
  availability is verified **before** the service is created (FR-004).
- **The semantic free allowance is exhausted mid-comparison.** Requests then
  return a billing error rather than a charge; the affected runs are re-run in the
  next billing period or the question set is reduced. No spend results either way.
- **The corpus exceeds the vector quota.** Indexing fails outright rather than
  degrading. Mitigated by measuring the quota (US2) before loading everything, and
  by the compression levers if needed.
- **A free search service is deleted after prolonged inactivity.** Documented
  behaviour. Nothing may depend on the service surviving the two-week absence; all
  inputs must be reproducible from the repository.
- **The block 3 Foundry account name is still soft-deleted.** Deploy into an
  unused resource-group name rather than purging, which is irreversible.
- **A question's answer is genuinely absent from the corpus.** Retrieval cannot
  succeed; the case is kept as a control rather than deleted, because a method
  that "finds" something for it is exhibiting a defect.
- **Labels disagree with what the author believes.** The labels are the ground
  truth for the scores; where the belief was wrong, the label wins and the
  correction is recorded.

---

## Requirements *(mandatory)*

### Functional Requirements

**Corpus and ingestion**

- **FR-001**: The corpus MUST be small enough that embedding it costs cents, and
  MUST be material the author can label accurately without external reference.
- **FR-002**: Content MUST be split into chunks whose size and overlap are stated
  explicitly, with the token distribution of the source measured first rather than
  a recommended constant applied blind.
- **FR-003**: Ingestion MUST NOT require a credential that the repository's
  existing practice would refuse, unless the tier makes that impossible and the
  downgrade is recorded with its cause.

**Search service**

- **FR-004**: Regional availability of semantic ranking MUST be verified **before**
  the search service is created, because the Free tier permits one service per
  subscription.
- **FR-005**: The search service MUST be on the Free tier. No configuration step
  in this feature may raise it.
- **FR-006**: The semantic billing plan MUST remain the free plan. (On the Free
  tier the standard plan is unavailable, which makes this structural rather than a
  matter of care — that fact MUST be recorded.)
- **FR-007**: The index MUST support keyword search, vector search, and semantic
  ranking over the same documents, so the four retrieval shapes differ only in the
  query.

**Measurement**

- **FR-008**: A labelled question set MUST exist, with **graded** relevance
  judgments per document, and MUST be version-controlled as a repository artifact.
- **FR-009**: The declared label range MUST match the labels actually used.
- **FR-010**: Retrieval quality MUST be scored by a metric set that requires no
  judge model and no pass threshold.
- **FR-011**: Both a recall-shaped and a ranking-shaped metric MUST be reported.
  Reporting only one is insufficient, because a ranking can be excellent over a
  result set that missed almost everything.
- **FR-012**: The label-sanity metric MUST be reported alongside the quality
  metrics, and a high value MUST invalidate the comparison rather than be omitted.
- **FR-013**: All four methods MUST be scored against the same question set,
  the same labels and the same index.
- **FR-014**: Evaluation results MUST be read directly from the evaluator's
  return value, not retrieved through the trace store, because block 4's finding
  F6 is still open.

**The two debts**

- **FR-015**: `infra/foundry.bicep` MUST assign the inference role prescribed by
  current documentation, by **role-definition identifier** rather than display
  name, and MUST NOT assign any role whose name begins with "Cognitive Services".
- **FR-016**: An inference call MUST be made under that role alone, and its
  outcome recorded — success as a confirmation, failure as a finding.
- **FR-017**: The template MUST be deployed twice consecutively with no manual
  intervention between the runs, and both outcomes recorded.
- **FR-018**: The template MUST deploy an embedding model deployment in addition
  to the chat model, both per-token.

**Cost and disposal**

- **FR-019**: Every resource created MUST appear in the Cost section below with
  its daily rate and its deletion command **before** it is created.
- **FR-020**: No fine-tuning training job and no fine-tuned model deployment may
  be created.
- **FR-021**: A full idle day MUST be observed before teardown, with at least one
  other billing scope active on the same day as a control — an absent line is only
  a measured zero when something else in the same window produced one.
- **FR-022**: Teardown MUST leave nothing behind, verified rather than assumed.

**Documentation**

- **FR-023**: The measured retrieval comparison MUST be published as a table,
  stating what was measured, on what corpus, and what it does not prove.
- **FR-024**: Where a measurement confirms one of the six research notes, the note
  MUST gain a verification beside the claim. Where it contradicts one, a finding
  MUST be recorded naming which of the two is wrong.

### Key Entities

- **Corpus**: the body of text to be retrieved over. Small, local, well
  understood by the author, version-controlled.
- **Chunk**: one retrievable unit, carrying its text, its vector, and enough
  provenance to identify the source document it came from.
- **Question set**: the queries used for measurement, each with graded relevance
  judgments over corpus documents. The longest-lived artifact this feature
  produces — every future comparison re-uses it, and it is the only deliverable
  here that no command can regenerate.
- **Retrieval run**: one question set executed under one retrieval method,
  producing ranked results with scores.
- **Comparison**: the scored table across all four retrieval runs.
- **Finding**: a recorded divergence between what a source prescribes and what a
  measurement observed, naming which is wrong and on what evidence.

---

## Cost *(mandatory — nothing is created before it appears here)*

All rates EUR, from the Azure Retail Prices API read 2026-08-27. Full derivation
in `docs/exam-notes/rag-cost-model.md`.

### Created by this feature

| Resource | Rate at rest | Deletion |
| --- | --- | --- |
| Azure AI Search, **Free** tier | **0,0000 €/hour = 0,00 €/day** | `az search service delete -n <service> -g <rg> --yes` |
| Foundry account + project | **0,00 €/day** (measured, block 3 T027) | `az group delete -n <rg> --yes --no-wait` |
| Chat model deployment, per-token | **0,00 €/day** at rest | deleted with the group |
| Embedding model deployment, per-token | **0,00 €/day** at rest | deleted with the group |

**Nothing in this feature bills at rest.** The whole spend is token-metered and
therefore bounded by the author's attention rather than by the calendar — the
"variable" class in this project's cost taxonomy, the one that has never caused a
surprise.

### Consumption

| Item | Rate | Estimate |
| --- | ---: | ---: |
| Embedding the corpus once (`text-embedding-3-large`, regional) | 0,0002 €/1K | ≈ **0,02 €** for the ~55.000-token corpus |
| Query embeddings | 0,0002 €/1K | negligible |
| Semantic ranker queries, free plan | **0,0000 €/1K** | 0,00 €, with a billing error as the wall |
| Chat completions, if any | 0,0004 / 0,0014 €/1K in-out | negligible at this volume |

**Expected total for the feature: well under 1 €.** Block 3's entire build cost
~1.300 tokens.

### Excluded by decision, with the figures that excluded them

| Excluded | Rate | Why |
| --- | ---: | --- |
| AI Search **Basic** | 0,0887 €/h = **2,13 €/day** | does not stop; 17 € over this block, ~30 € more during the absence |
| **Fine-tuned model hosting** | 1,4937 €/h = **35,85 €/day** | flat across model sizes; inference no cheaper than the base model; break-even is ~25 million output tokens per day against a project that spent ≈0,81 € in all of August |
| Fine-tuning training | 4,40–5,80 €/1M tokens | affordable on its own, and useless without the hosting above |
| Provisioned throughput | 13,16 €/h | already excluded in block 3 |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The four retrieval methods produce four sets of retrieval-quality
  scores over one labelled question set, published as a single table, and the
  best method is identified by the numbers rather than chosen.
- **SC-002**: The record states explicitly whether the measured ordering matches
  the ordering the source asserts, and — because the source publishes no margin —
  reports the margin as a new fact rather than as a confirmation.
- **SC-003**: The label-sanity metric is reported for every run, and its value is
  low enough that the quality metrics are meaningful; if it is not, the comparison
  is declared unreliable rather than published.
- **SC-004**: Both a recall-shaped and a ranking-shaped metric are reported for
  every method, and the record shows at least one case where they disagree — or
  states that none occurred.
- **SC-005**: The free search service's actual storage quota and vector index
  quota are read from the service itself and recorded, together with whether they
  confirm or contradict the 50 MB inference that the documentation left open.
- **SC-006**: The corpus's measured vector index size is recorded and compared
  against the size the documented formula predicts.
- **SC-007**: An inference call succeeds with only the prescribed Foundry role
  assigned and no Cognitive Services role present anywhere in the template — or
  its failure is written up as a finding.
- **SC-008**: Two consecutive deployments of `infra/foundry.bicep` both succeed
  with no manual intervention between them.
- **SC-009**: After teardown, listing resources in the feature's resource group
  returns nothing, and the group no longer exists.
- **SC-010** *(cost)*: On a full day with every resource in place and no calls
  made, the feature's resource group contributes **no cost line**, while at least
  one other scope in the same subscription produces one on that same day. An
  absent line without a control is not a measured zero.
- **SC-011** *(cost)*: No fine-tuning training job and no fine-tuned deployment
  exists at any point — verified by listing deployments, not by recollection — and
  the hosting rate that excluded it is written in this spec.
- **SC-012**: Each of the six research notes either gains a verification beside a
  claim this feature confirmed, or a finding recording a claim it contradicted.

---

## Out of Scope

- **Chunk-size sweep.** Cut deliberately at spec time: varying chunk size
  re-embeds the entire corpus per cell, while varying retrieval method re-uses one
  embedded corpus. The expensive axis and the cheap axis are not the same axis,
  and 8 days buys the cheap one. Documented in
  `rag-chunking-strategies.md` § 7; revisit only if US1 and US2 close early.
- **Fine-tuning, executed.** Priced above and closed as theory. The decision
  content is in `fine-tuning-vs-rag.md` and is fully examinable without it.
- **Quantization and compression, measured.** The levers and Learn's published
  sample figures are in `rag-vector-store-and-indexing.md` § 6. Building a second
  index to measure them locally is the first thing to add if time remains, and the
  second thing to cut if it does not.
- **Integrated vectorization via an indexer and skillset.** Blocked in practice by
  the tier's lack of indexer managed identity and its 1–3 minute run limit; the
  mechanism is documented, not built.
- **Agentic retrieval and knowledge bases.** Adjacent, newer, and not what Domain
  5 asks about.
- **An end-to-end chat application over the index.** The generation half is block
  3 and block 4's territory; this feature stops at retrieval, which is where the
  unmeasured question is.
- **Backfilling Learn notes for domains 1, 2 and 4.** Scheduled for the return,
  when the environment is destroyed and time is fragmented.

---

## Assumptions

- **The corpus is this repository's own `docs/exam-notes/`** — ~284 KB, ~41.600
  words, ~55.000 tokens across 18 notes. Chosen because it is local, free, already
  version-controlled, and material the author knows well enough to label
  accurately, which is the scarcest input to US1. At ~2.000-character chunks it
  yields roughly 190 chunks and an estimated vector index in the low single-digit
  megabytes — comfortably inside 50 MB, so the tier constraint does not bind.
- **The question set is about 20 questions**, sized to be labelled in one sitting
  and re-run cheaply.
- **The search service goes in the same region as the Foundry account**
  (`swedencentral`), subject to FR-004's prior check on semantic-ranker
  availability. If that region does not offer semantic ranking, the region
  decision is reopened before anything is created — not after.
- **Ingestion is push-based**: chunking and embedding happen locally and documents
  are pushed to the index over the data plane. This preserves the repository's
  credential-less posture, which an indexer on the Free tier could not, and
  removes the indexer runtime and enrichment caps as constraints. The alternative
  — an indexer with a key-bearing connection string — is rejected here and the
  rejection is itself part of US2's record.
- **The embedding model is `text-embedding-3-large`**, deployed per-token. It is
  the smallest model whose price the retail API publishes at usable precision;
  `text-embedding-3-small` is published as literal `0.0` in EUR, which is a
  rounding artifact rather than a free model, and building a cost argument on it
  would repeat a mistake this project has already made once.
- **Deployment is manual, from the CLI, not through CI.** `infra/foundry.bicep`
  has never been deployed by the pipeline, and the CI identity's role does not
  cover `Microsoft.Search`. Adding a resource type to a CI-deployed template would
  fail the next run by design; that is not a debt this feature takes on.
- **A new resource group name is used**, avoiding the block 3 account name's
  48-hour soft-delete window and the Key Vault 90-day name hold.

---

## Dependencies

- An empty subscription state, as of 2026-08-27: zero resource groups, zero spend.
- `infra/foundry.bicep`, carrying block 4's fixes F1–F3, which US3 both depends on
  and tests.
- The six research notes listed in Context, which the constitution requires to
  exist before the plan freezes. They do.
- Block 4's finding F6, open, which FR-014 routes around rather than resolves.
