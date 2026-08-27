---

description: "Task list for Block 5 — RAG retrieval quality, measured"
---

# Tasks: Block 5 — RAG Retrieval Quality, Measured

**Input**: Design documents from `/specs/008-rag-retrieval-quality/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: no unit-test suite. This feature verifies by observation, as blocks 3
and 4 did — the scoring run is US1's test, the two service-statistics calls are
US2's, and two consecutive deployments plus one inference call are US3's.

**Organization**: grouped by user story. ⚠️ **Priority order and execution order
are not the same here**, and the spec says so: US3 runs first in wall-clock time
because it produces the model deployments the other two consume, while being the
story to drop first if the block collapses.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete work)
- **[Story]**: US1, US2, US3
- **€**: the task spends money. Every other task is free.

---

## Phase 1: Setup — pre-flight and scaffolding

**Purpose**: everything that must be true before a template is written, plus the
local project. Three of these checks exist because a green-looking command
already reported the wrong thing once ([research.md](./research.md) R1, R3, R8).

- [X] T001 Register the resource provider: `az provider register -n Microsoft.Search`, then poll `az provider show -n Microsoft.Search --query registrationState -o tsv` until it reports `Registered` — it was **`NotRegistered`** on 2026-08-27 and an unregistered provider fails deployment with `MissingSubscriptionRegistration`, which reads like an authorization refusal (research.md § R1)
- [X] T002 [P] Confirm the subscription is still empty: `az group list --query "[].name" -o tsv` returns nothing, and `az cognitiveservices account list-deleted` returns `[]`
- [X] T003 [P] Re-read the embedding quota live and record it: `az cognitiveservices usage list -l swedencentral --query "[?contains(name.value,'text-embedding-3-large')].{n:name.value,l:limit}" -o table`. Expected `Standard` **350**, `GlobalStandard` **0** — this decides one line of `infra/foundry.bicep` (research.md § R3)
- [X] T004 [P] Re-read the chat quota: `OpenAI.GlobalStandard.gpt4.1-mini` limit ≥ 10. Note the meter spells the model `gpt4.1-mini`, without the first hyphen
- [X] T005 Create the resource group: `az group create -n rg-ai300-rag -l swedencentral`. A **new** name, so `uniqueString(resourceGroup().id)` yields names no soft-deleted resource can shadow (research.md § R4)
- [X] T006 [P] Create `rag-optimization/rag-block5/` with `pyproject.toml`, pinning `azure-search-documents>=12.0.0,<13`, `azure-ai-evaluation>=1.18.3,<2`, `azure-identity>=1.19,<2`, `openai>=1.60,<2`, `tiktoken>=0.8,<1` (research.md § R10), then `uv sync`
- [X] T007 [P] Add `rag-optimization/rag-block5/runs/` to `.gitignore` — run files are regenerable from the index; the label set is not and stays tracked

**Checkpoint**: provider registered, quotas known, resource group exists, local environment resolves.

---

## Phase 2: Foundational — the environment, and the plumbing every story needs

**⚠️ CRITICAL**: no story's measurement can run until this phase completes.

### The two template changes

- [X] T008 In `infra/foundry.bicep`, replace the `Cognitive Services OpenAI User` grant (lines 411–427) with **Foundry User** by GUID `53ca6127-db72-4b80-b1b0-d745d6d5456d`, at the account scope. Rewrite — do not delete — the comment block above it: the discovery of the `401` stays, with a new paragraph explaining that the role that *worked* was not the role that is *prescribed* (contracts/foundry-redeployment.md, change 1)
- [X] T009 In `infra/foundry.bicep`, add a `text-embedding-3-large` deployment: `sku.name` **`Standard`** (not `GlobalStandard` — T003), capacity 10, `model.version: '1'` pinned, `versionUpgradeOption: 'NoAutoUpgrade'`
- [X] T010 ⚠️ Chain T009's deployment into the existing dependency sequence so the order is `account → gpt-4.1-mini → text-embedding-3-large → project → account connection → project connection`. Two sibling `accounts/deployments` contend for the same account-level lock and race; block 4 paid four failed deployments to learn this, and neither `az bicep build` nor `what-if` can see it (research.md § R5, findings F1)
- [X] T011 Write `infra/search.bicep`: `Microsoft.Search/searchServices@2025-05-01`, `sku.name: 'free'`, `semanticSearch: 'free'`, `disableLocalAuth: true`, **`authOptions` omitted entirely** (the two are mutually exclusive), `replicaCount: 1`, `partitionCount: 1`, `hostingMode: 'default'` (contracts/search-service-and-index.md § 1)
- [X] T012 In `infra/search.bicep`, add two caller role assignments at the service scope, by GUID: **Search Service Contributor** `7ca78c08-252a-4471-8644-bb5ff32d4ba0` and **Search Index Data Contributor** `8ebe5a00-799e-43f5-93ac-243d3dce84a7`. Both are needed and the first is the non-obvious one — the data role alone cannot read `/servicestats`, which is SC-005's whole measurement (research.md § R7)

### Validation and first deployment

- [X] T013 `az bicep build -f infra/foundry.bicep` and `az bicep build -f infra/search.bicep`. Report warnings as warnings. This proves syntax and nothing else
- [X] T014 `az deployment group what-if` for both templates against `rg-ai300-rag`. Region eligibility and resource-name length surface here and nowhere earlier
- [X] T015 Deploy `infra/foundry.bicep` as `block5-001` with `callerPrincipalId=$(az ad signed-in-user show --query id -o tsv)`. On failure, capture `az deployment operation group list` and identify the **specific resource** before changing anything
- [X] T016 Deploy `infra/search.bicep` as `block5-search-001` with the same caller
- [X] T017 Verify the Log Analytics workspace was **created, not restored**: `az monitor log-analytics workspace show -g rg-ai300-rag -n <ws> --query createdDate -o tsv` returns today. A silent restore reports as a successful create (block 4 § F8)

### The plumbing the stories share

- [X] T018 Write `rag-optimization/rag-block5/chunk_corpus.py`: read `docs/exam-notes/*.md`, measure the token distribution with `tiktoken` **first** and print it (FR-002), then split on H2 boundaries and window sections over the cap at **512 tokens / 128 overlap**, emitting chunks with `chunk_id`, `note`, `heading`, `content`, `token_count`, `corpus_commit` (data-model.md § 2)
- [X] T019 Write `rag-optimization/rag-block5/create_index.py`: the index schema per data-model.md § 3 — searchable `content` and `heading`, filterable `note`/`token_count`/`corpus_commit`, `content_vector` as `Collection(Edm.Single)` at 3072 dimensions on an HNSW cosine profile, and one semantic configuration named `default` with `heading` as title and `content` as content
- [X] T020 Write `rag-optimization/rag-block5/service_stats.py`: reads `/servicestats` and `/indexes/<index>/stats` over the data plane with an Entra ID token from `az account get-access-token --scope https://search.azure.com/.default`, and prints raw JSON
- [X] T021 Run `service_stats.py` against the **empty** service and save the raw output. This is also the RBAC smoke test: a `403` here means T012's role split, not the tier
- [X] T022 Run `create_index.py` against the service and confirm the index exists with the semantic configuration attached
- [X] T023 Write `rag-optimization/rag-block5/embed_and_push.py`: embed each chunk with the `text-embedding-3-large` deployment through the `openai` SDK using an Entra token, and push documents over the data plane in batches. **No key anywhere** (contracts/search-service-and-index.md § 4)
- [ ] T024 **€** Run `embed_and_push.py` once. ≈55.000 tokens at 0,0002 €/1K ≈ **0,011 €**. Record the actual token count consumed

**Checkpoint**: both templates deployed once, index populated, service statistics readable. All three stories can now proceed.

---

## Phase 3: User Story 3 — Two debts on `foundry.bicep`, settled (P3, runs first)

**Goal**: the template grants the role current documentation prescribes, and its
re-runnability survives the change.

**Independent test**: deploy the template twice into the resource group and make
one inference call. Needs no search service and no corpus.

- [X] T025 [US3] Deploy `infra/foundry.bicep` again as `block5-002`, **immediately**, with no manual step and no portal fix between the runs. Both outcomes recorded (FR-017, SC-008)
- [X] T026 [P] [US3] Deploy `infra/search.bicep` again as `block5-search-002`. Re-runnability is a property this repository tests rather than hopes for
- [X] T027 [US3] Confirm both model deployments are per-token: `az cognitiveservices account deployment list -n <account> -g rg-ai300-rag --query "[].{n:name,sku:sku.name}" -o table` shows `GlobalStandard` and `Standard`, and **no** name containing `Provisioned` (FR-018, spec constraint 5)
- [X] T028 [US3] Confirm no Cognitive Services role survives anywhere: `az role assignment list --scope <account-id> --query "[].roleDefinitionName" -o tsv` contains `Foundry User` and nothing beginning with `Cognitive Services` (FR-015)
- [X] T029 [US3] **€** Make one inference call under that role alone: `cd genaiops/foundry-block3 && uv run call_model.py`, reused unchanged. Fractions of a cent
- [X] T030 [US3] Record T029's outcome, **without having assumed it** (FR-016, SC-007). **Success** → `infra/foundry.bicep`'s grant becomes the only line in this repository both measured and prescribed; add the verification to `docs/exam-notes/foundry-rbac-and-authentication.md` § 3 and correct `genaiops/foundry-block3/README.md` where it documents the old path. **Failure** → write the finding: the verbatim refusal, the role assigned, the data action named, which of source and measurement is wrong — then restore the older grant **with the finding cited beside it**, never silently

**Checkpoint**: US3 complete and independently demonstrable.

---

## Phase 4: User Story 2 — The Free tier's real envelope (P2)

**Goal**: what the free service actually permits, as numbers, including the one
the documentation does not publish.

**Independent test**: read the service's own statistics. No labels, no evaluation
apparatus, no question set.

- [ ] T031 [US2] From T021's saved output, record the storage quota and — the point of the story — the **vector index quota**, and state whether they confirm or contradict the inference that the 50 MB service storage limit binds first. Learn's quota table has columns for Basic through L2 and **no Free column** (FR-004 context, SC-005)
- [ ] T032 [US2] Record the index / indexer / datasource / skillset counters returned alongside, against the published 3 / 3 / 3 / 3
- [ ] T033 [US2] Run `service_stats.py --index` after ingestion and record `documentCount`, `storageSize` and `vectorIndexSize`; compare the measured vector size against the documented formula's prediction (≈145 × 3072 × 4 B ≈ 1,8 MB). A gap is a result, not something to reconcile away (SC-006)
- [ ] T034 [US2] Record the chunk-count and token-distribution report T018 printed, and state which of Learn's two mutually inconsistent chunk-size recommendations was followed and which was not (`rag-chunking-strategies.md` § 2)
- [ ] T035 [US2] Write up the ingestion-path decision and its cause: the Free tier grants **no managed identity for indexer outbound connections**, so integrated vectorization would require a key-bearing connection string. Push-based ingestion preserved the credential-less posture; FR-003's downgrade clause stayed dormant (US2 scenario 3)
- [ ] T036 [P] [US2] Capture verbatim any refusal the tier produced during this phase — attempted second index, a `403` from the wrong role, a quota rejection. **The refusal is the evidence** (US2 scenario 4). If none occurred, say so explicitly rather than leaving the section empty

**Checkpoint**: US2 complete. It needs nothing from US1 and survives if time runs short.

---

## Phase 5: User Story 1 — The retrieval ladder, measured against labels (P1)

**Goal**: how much retrieval quality actually changes across the four methods, as
a number produced by a labelled ground truth.

**Independent test**: run the four shapes over the populated index and produce a
scored table.

⚠️ **Ordering**: retrieval runs **before** labelling. Labels are pooled from what
the methods actually returned, or `holes_ratio` measures label coverage instead
of retrieval quality (research.md § R9).

- [ ] T037 [US1] Write `rag-optimization/rag-block5/questions/questions.jsonl`: ~20 questions with `question_id`, `query`, the author's prior (`note`), and `kind`. **At least one `control`** whose answer is genuinely absent from the corpus — kept, never deleted, because a method that "finds" something for it is exhibiting a defect (FR-008, spec Edge Cases)
- [ ] T038 [US1] Write `rag-optimization/rag-block5/run_retrieval.py` with `--method keyword|vector|hybrid|hybrid_semantic`, top-10, embedding each query **once** and reusing it across methods. Each result row records the score **and** `score_field` — `@search.score` for the first three, `@search.rerankerScore` for the fourth (contracts/retrieval-and-scoring.md § 1, data-model.md § 5)
- [ ] T039 [US1] **€** Run all four methods over the question set. Query embeddings only; semantic ranking bills on the free plan and stops with a billing error rather than a charge. Confirm no re-embedding of the corpus occurred (US1 scenario 5)
- [ ] T040 [US1] Write and run `rag-optimization/rag-block5/pool_for_labelling.py`: the union of every chunk any of the four methods returned, emitted ready to label
- [ ] T041 [US1] Label the pool by hand into `questions/labels.jsonl`, graded **0–3** per data-model.md § 6. Where the author's prior and the label disagree, **the label wins** and the correction is recorded (spec Edge Cases). This is the only artifact here no command can regenerate — it is committed
- [ ] T042 [US1] Write `rag-optimization/rag-block5/score_retrieval.py` using `DocumentRetrievalEvaluator` with **explicit** `ground_truth_label_min=0, ground_truth_label_max=3`. ⚠️ The SDK defaults are `0`/`4` and Learn's own example passes `1`/`5`; `fidelity` weights labels over `range(min+1, max+1)`, so a range one point off reweights the metric silently instead of raising (FR-009, research.md § R8)
- [ ] T043 [US1] Read results **from the evaluator's return value in-process**, never through the trace store — block 4's F6 is closed as a known limitation and fails toward under-reporting (FR-014)
- [ ] T044 [US1] Check `holes_ratio` **before** publishing anything. If it is high, extend the pool (T040) and label again (T041). A comparison over unjudged documents is declared unreliable, not published with a caveat (FR-012, SC-003, US1 scenario 3)
- [ ] T045 [US1] Produce `rag-optimization/rag-block5/results/comparison.md`: one table, four methods, with `ndcg@3` (ranking-shaped) and `fidelity` (recall-shaped) as the headline pair, plus `xdcg@3`, `top1_relevance`, `top3_max_relevance`, `holes`, `holes_ratio`. The evaluator's `*_passed` labels are recorded beside the scores and decide nothing (FR-011, SC-001)
- [ ] T046 [US1] State in words whether the measured ordering matches what the source asserts, and report the **margin** — which Learn does not publish anywhere, on either the hybrid overview or the ranking page. A margin is a new fact, not a confirmation; a broken ordering is a finding (SC-002)
- [ ] T047 [US1] Identify at least one case where the recall-shaped and ranking-shaped metrics **disagree**, or state explicitly that none occurred. Learn's own worked example pairs `ndcg@3` 0.646 `pass` with `fidelity` 0.019 `fail` — an excellent ranking over a result set that missed nearly everything (SC-004)
- [ ] T048 [US1] Write up one worked example in prose: a question where keyword retrieval fails and vector succeeds, or the reverse. The numbers say which method wins; the example says what each method is *for* (US1 scenario 4)

**Checkpoint**: US1 complete. The feature's principal deliverable exists.

---

## Phase 6: Polish — documentation, cost, disposal

- [ ] T049 [P] Draft `rag-optimization/rag-block5/README.md` in the author's first person, for review — never committed by tooling (Principle IV)
- [ ] T050 [P] Document the **corpus as a case study**: this repository's own notes, indexed into the service they describe. What it buys — accurate labels, zero acquisition cost, full reproducibility from the tree — against what it costs in external validity: small, homogeneous, single-author, and labelled by the person who wrote it, which no metric here detects (FR-023)
- [ ] T051 [P] Document the **local-embedding decision as a case study**: push-based ingestion against the indexer-with-integrated-vectorization path Learn's tutorials take, unavailable here for two independent Free-tier reasons. The mechanism not used is documented beside the one that was
- [ ] T052 Write `specs/008-rag-retrieval-quality/findings.md` in block 4's format — severity, the command, the verbatim output, which of source and measurement is wrong and on what evidence
- [ ] T053 Close the constitution 1.1.0 loop: each of the six research notes gains a **verification** beside a claim this feature confirmed or a **finding** recording one it contradicted (FR-024, SC-012). Two are owed already: `rag-hybrid-search-and-ranking.md` — free-tier semantic ranking also depends on the **region**, not only the billing plan (research.md § R2); and `rag-vector-store-and-indexing.md` / `rag-cost-model.md` — a model advertised by `model list` can have **zero quota** on that SKU (§ R3)
- [ ] T054 **€** Observe a full idle day: no calls to the search service, and **one deliberate chat call** that day to produce the control line. The subscription contains nothing else, so an empty result would be an absent dataset rather than a measured zero (research.md § R11, FR-021)
- [ ] T055 Query Cost Management at **resource** granularity for the idle day — `az costmanagement query --type ActualCost --timeframe Custom`, not `az consumption usage list`, which returns `cost: None` on this subscription. Expected: a line for the Foundry account, **no line** for the search service (SC-010). Run a day or two later; ingestion lags, as blocks 2 and 3 both found
- [ ] T056 Verify no fine-tuning artifact was ever created: `az cognitiveservices account deployment list -n <account> -g rg-ai300-rag -o table` shows no `*-ft` deployment, and no training job exists. Verified by listing, not by recollection (SC-011, FR-020)
- [ ] T057 Tear down: `az group delete -n rg-ai300-rag --yes`, then `az monitor log-analytics workspace list-deleted-workspaces -o table` and force-delete this feature's workspace if it appears (block 4 § F8). ⚠️ A free search service being «deleted after extended periods of inactivity» is documented behaviour, **not** a teardown mechanism
- [ ] T058 Confirm teardown rather than assuming it: `az group exists -n rg-ai300-rag` returns `false` and `az resource list -g rg-ai300-rag` errors on a missing group (SC-009, FR-022)
- [ ] T059 ⚠️ Do **not** approve the CI deployment gate this branch queues on merge. `infra-deploy.yml` triggers on any `infra/**` change and would deploy `main.bicep` — the classical-ML stack, which does bill at rest (research.md § R13)

---

## Dependencies

```text
Phase 1 Setup  ──▶ Phase 2 Foundational ──┬──▶ Phase 3 US3 ──┐
                                          ├──▶ Phase 4 US2 ──┼──▶ Phase 6 Polish
                                          └──▶ Phase 5 US1 ──┘
```

- **T001 blocks everything.** An unregistered provider fails T016 outright.
- **T003 blocks T009.** The quota reading is what decides `Standard` over `GlobalStandard`.
- **T010 blocks T015 and T025.** Without the chain, the deployment races and fails about half the time — the worst rate, because it passes often enough to look fixed.
- **T012 blocks T021.** The wrong role produces a `403` that reads like a tier limitation.
- **T024 blocks T033, T039.** Nothing can be measured or retrieved over an empty index.
- **T039 blocks T040 blocks T041 blocks T042.** Pooled labelling is why retrieval precedes labelling.
- **T044 gates T045–T048.** A high `holes_ratio` sends work back to T040, not forward.
- **T054 blocks T055**, and T055 lags by a day or two on Cost Management ingestion.
- **T057 must come last.** Teardown destroys everything US1 and US2 measure.

**Story independence**: US3 needs no search service and no corpus. US2 needs no
question set and no labels. US1 needs the populated index that Phase 2 builds.

---

## Parallel opportunities

- **T002, T003, T004** — three independent read-only quota and state checks.
- **T006, T007** — local scaffolding, unrelated to Azure.
- **T008/T009/T010 with T011/T012** — two different template files; the second is a new file entirely.
- **T025 and T026** — the two second deployments target different resource types.
- **T036** runs alongside the rest of Phase 4.
- **T049, T050, T051** — three separate documentation pieces.

Everything in Phase 5 is sequential. It is one measurement pipeline, and that is
the point of it.

---

## Implementation strategy

**Execution order is US3 → US2 → US1**, not P1 → P2 → P3. US3 produces the model
deployments the others consume; US2's index is what US1 queries.

**MVP, if only one story could ship**: US1 — the four-method comparison against a
labelled ground truth. It is Domain 5's core content and the one deliverable the
source cannot supply.

**If time runs short, cut in this order** and say what was cut rather than
leaving it open:

1. **T048** — the worked example in prose. The table stands without it.
2. **T029–T030** — US3's role measurement. The redeployment still happens; only
   the debt goes unsettled, and it is already a written debt.
3. **Never US2.** Cheapest story, no labels required, and it produces the number
   Learn does not publish.

Not on the list because it was cut at spec time: the chunk-size sweep.
Reinstating it re-embeds the whole corpus once per cell — the expensive axis,
where varying the retrieval method is the cheap one.

**Commits split four ways**, one logical change each: the two template changes;
the workload scripts; the question set and labels; the results and note
verifications. Proposed to the author, never executed (Principle III).
