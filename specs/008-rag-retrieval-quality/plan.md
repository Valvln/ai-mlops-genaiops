# Implementation Plan: Block 5 — RAG Retrieval Quality, Measured

**Branch**: `008-rag-retrieval-quality` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-rag-retrieval-quality/spec.md`

## Summary

Deploy `infra/foundry.bicep` — with two changes — and a new `infra/search.bicep`
into one disposable resource group in `swedencentral`, chunk and embed this
repository's own `docs/exam-notes/` locally, push them into a **Free-tier** Azure
AI Search index, then run one question set through four retrieval shapes
(keyword, vector, hybrid, hybrid + semantic ranking) and score all four against a
pooled, hand-labelled ground truth with the SDK's `DocumentRetrievalEvaluator` —
which makes no model call and applies no judge.

The deliverable is the **margin** Learn asserts and does not publish, plus the
Free tier's **vector index quota**, which Learn's quota table omits entirely.

Five findings from this session's live checks shape the plan more than the spec's
own assumptions did. Three of them would have failed a deployment:

- **`Microsoft.Search` is `NotRegistered` on this subscription** — an
  unregistered provider fails with `MissingSubscriptionRegistration`, which reads
  like an authorization refusal and is not one ([research.md § R1](./research.md)).
- **`text-embedding-3-large` has zero `GlobalStandard` quota in `swedencentral`**,
  while `az cognitiveservices model list` advertises the SKU as available.
  Regional `Standard` has 350. Model availability and deployable quota are
  different facts, and only the second is a quota query ([§ R3](./research.md)).
- **Adding the embedding deployment reintroduces block 4's F1 race** unless it is
  chained rather than declared beside the chat deployment. Every child of a
  Cognitive Services account contends for the same lock; a sibling pair fails
  about half the time, which is worse than always ([§ R5](./research.md)).
- **`swedencentral` is confirmed correct and `northeurope` is doubly
  disqualified** — no free-tier semantic ranker, and new search services cannot
  be created there at all. FR-004's pre-creation check is therefore satisfied
  *at plan time* rather than deferred ([§ R2](./research.md)).
- **`DocumentRetrievalEvaluator` exists but is absent from the stable package
  reference, and its label-range defaults disagree with Learn's own example**
  (SDK `0..4`, documentation `1..5`). `fidelity` weights labels over
  `range(min+1, max+1)`, so a range declared one point off reweights the metric
  silently instead of raising ([§ R8](./research.md)).

Two further decisions the spec left implicit and this plan settles: labels are
built by **pooling** the union of what all four methods retrieved, which puts
retrieval *before* labelling ([§ R9](./research.md)); and the at-rest cost
measurement needs a **control line inside the same resource group**, because the
subscription contains nothing else to compare against ([§ R11](./research.md)).

## Technical Context

**Language/Version**: Bicep for IaC — `infra/foundry.bicep` modified (two
changes), `infra/search.bicep` new. Python 3.11 for the workload, `uv`-managed,
matching `genaiops/foundry-block3` and `qa-observability/foundry-block4`.

**Primary Dependencies**: `azure-search-documents>=12.0.0,<13` (12.0.0 is the
current stable; 12.1.0b1 is a beta and is not taken),
`azure-ai-evaluation>=1.18.3,<2` (`DocumentRetrievalEvaluator`, verified present
at that tag), `azure-identity`, `openai` (embeddings, called with an Entra
token), `tiktoken` (local and free — measures the corpus token distribution
before chunking, per FR-002). Pins verified against PyPI 2026-08-27
([research.md § R10](./research.md)).

**Storage**: one Azure AI Search index on the **Free** tier — vector fields,
searchable text and a semantic configuration in a single index, so the four
methods differ only in the query. Runs are local JSONL and regenerable; the
label set is local JSONL and **committed**, because no command can reproduce it.
No storage account, no blob container, no datastore.

**Testing**: verification by observation, the pattern blocks 3 and 4 established.
The scoring run **is** the test for US1; `/servicestats` and `/indexes/*/stats`
are the tests for US2; two consecutive deployments plus one inference call are
the tests for US3. Evaluation results are read from the evaluator's return value
in-process, never through the trace store (FR-014, block 4 § F6).

**Target Platform**: `swedencentral` — Foundry account + project + **two**
per-token model deployments (`gpt-4.1-mini`, `text-embedding-3-large`), plus one
Free-tier search service, all in a new resource group `rg-ai300-rag`. Workload
runs locally (macOS, `uv`).

**Project Type**: RAG optimization workload. Code lives under
`rag-optimization/` — the last of the four topic folders in the constitution's
structure table still empty ([research.md § R12](./research.md)).

**Performance Goals**: none. Retrieval *quality* is the measurement; latency and
throughput are not.

**Constraints**: **0,00 €/day at rest for every resource created** — the Free
search tier is 0,0000 €/hour and both model deployments are per-token, so nothing
in this feature bills while idle. Total spend is one corpus embedding (≈0,011 €)
plus a handful of query embeddings and one control chat call. No fine-tuning job
and no fine-tuned deployment at any point (SC-011); hosting one is 1,4937 €/hour.
No provisioned SKU. No hub. Deployment is manual from the CLI, outside CI — the
CI identity's role does not cover `Microsoft.Search`, and widening it is
explicitly not this feature's work.

**Scale/Scope**: ~145 chunks from 18 notes (~55.000 tokens), 3072-dimension
vectors, ≈1,8 MB of vector index against a 50 MB tier limit, ~20 questions of
which at least one is an unanswerable control, 4 retrieval runs at top-10, one
pooled label set, one comparison table.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this plan satisfies it |
| --- | --- | --- |
| **I. Cost discipline** (non-negotiable) | ✅ Pass | Every resource appears in the spec's Cost section with a daily rate and a deletion command **before** creation, and this plan adds none beyond it. The cheapest suitable tier is not merely proposed but made structural: on the Free tier the standard semantic plan cannot be selected at all, so FR-006 is enforced by the service rather than by care. The one variable cost is a single corpus embedding whose upper bound is a measured token count, not an estimate. R3 raised the embedding rate from 0,0001 to 0,0002 €/1K on discovering the GlobalStandard quota is zero — the spec's Cost table already quotes the regional rate, so no published figure moves |
| **II. Version control hygiene** | ✅ Pass | `infra/*.json` build outputs stay gitignored; the `.bicep` files are the source. The Search API version (`2025-05-01`) and both role GUIDs were read from current reference documentation this session, not recalled. Run files are regenerable and untracked; the label set is committed because it is not regenerable |
| **III. Commit authorization** (non-negotiable) | ✅ Pass | No commit or push performed by this plan. The Spec Kit git extension's auto-commit hooks remain `optional: true` with `auto_commit.default: false`. The one mutating pre-flight action identified here (`az provider register -n Microsoft.Search`) is flagged for the author at implementation time, not performed by the plan |
| **IV. Documentation ownership** | ✅ Pass | `rag-optimization/rag-block5/README.md` is drafted for the author's review in the first person, never committed by tooling. The two case studies the author asked for — the self-referential corpus and the local-embedding decision — are documentation deliverables, carried into [contracts/retrieval-and-scoring.md § 5](./contracts/retrieval-and-scoring.md) and the quickstart's day 7 |
| **V. Validation before commit** | ✅ Pass | `az bicep build` on both templates, then `az deployment group what-if`, then **two consecutive deployments** for each. The plan states plainly which of these proves what: the build proves syntax, `what-if` catches region and name-length problems, and only the second deployment proves re-runnability. R5's chained embedding deployment is invisible to the first two |
| **VI. English only** | ✅ Pass | All artifacts in English |
| **VII. Folder structure** | ✅ Pass | `rag-optimization/` is the folder the constitution's table already reserves for this scope, and this is its first occupant. No new top-level folder proposed |
| **Sourced research before the plan freezes (1.1.0)** | ✅ Pass | Six notes in `docs/exam-notes/`, each with sources and a 2026-08-27 reading date, committed **before** this plan started (`8e83719`, `1fb0e59`, `59a48bb`). `research.md` is the internal decision record and does not stand in for them. FR-024 and SC-012 close the loop: each note ends this feature with a verification or a finding, and two are already owed at plan time (R2's regional gate, R3's quota gap) |

**Additional gates this repository has earned:**

| Gate | Status | Notes |
| --- | --- | --- |
| Never approve the deployment gate on the author's behalf | ✅ | R13 states plainly that this branch **will** queue a `main.bicep` deployment on merge, because `infra-deploy.yml` triggers on any `infra/**` change. It must be left unapproved — approving it deploys the classical-ML stack, which does bill at rest |
| Never widen the CI role with a built-in role | ✅ | `infra/ci-identity.bicep` is untouched. `Microsoft.Search` is deliberately absent from it; deployment is manual |
| Read the captured error, not the green summary | ✅ | Three pre-flight checks exist precisely because a green-looking command reported the wrong thing: `model list` advertises a SKU whose quota is zero (R3), `provider show` reports a state no deployment consults until it fails (R1), and the stable SDK reference omits a class that ships (R8) |
| A criterion that passes is not an objective met | ✅ | Two places. `holes_ratio` gates the comparison table rather than annotating it (SC-003) — Learn's own example pairs `ndcg@3` 0.646 `pass` with `fidelity` 0.019 `fail`. And R8 corrects FR-010's own wording: the evaluator has no judge but does carry seven thresholds, so the scores are reported and the `*_passed` labels are advisory |
| Deferred criteria declared in advance | ✅ | SC-010's at-rest measurement waits on Cost Management ingestion lag, as in blocks 2 and 3, and needs the R11 control call to be a measured zero rather than an absent dataset |
| The soft-delete trap, recognized on sight | ✅ | R4 checked both. No Cognitive Services account is soft-deleted; the two remaining Log Analytics workspaces belong to dead test groups, which shows block 4's F8 fix was actually applied. A **new** resource-group name makes a silent restore impossible by construction rather than by remembering to check |
| A measurement reports what happened, not what is prescribed | ✅ | US3 is this gate made into work. R6 assigns the prescribed role and **does not assume the call succeeds**; success is a verification, failure is a finding with the old grant restored beside it |

**Result: no violations. Complexity Tracking is therefore omitted.**

### Re-evaluation after Phase 1 design

- **Principle I held under design pressure.** Phase 1 added one resource type
  (the search service) that Technical Context already named, at the tier the spec
  fixed, and removed nothing from the Cost table. The design's one new cost fact
  — R3's regional embedding rate — was already the rate the spec quoted.
- **Principle V gained a sharper statement.** The contracts now say which
  validation step can see which defect, rather than listing three commands as
  though they were interchangeable. R5's race is the worked example: it is
  invisible to `az bicep build` and to `what-if`, and only deploy #2 can see it.
- **One spec wording correction surfaced and is recorded rather than silently
  applied.** FR-010 asks for a metric set with «no judge model and no pass
  threshold». The first half is exactly right; the second is not, because the
  evaluator carries seven thresholds of its own. The design keeps FR-010's
  *intent* — nothing here is decided by a model or by a threshold — and reports
  the raw scores. Flagged for the author; no spec edit made without authorization.
- **One spec mechanism needed refining, not changing.** SC-010 asks for a control
  scope in the same subscription on the idle day. There is none — the
  subscription is empty. R11 supplies the control from inside the same resource
  group, at resource granularity. The criterion is unchanged; only the way it is
  satisfied is now specified.
- **No new violations.** The gate passes after design as it did before.

## Project Structure

### Documentation (this feature)

```text
specs/008-rag-retrieval-quality/
├── plan.md                          # This file
├── spec.md                          # Feature specification (committed, abd8e9e)
├── research.md                      # Phase 0 — 13 decisions, live-verified today
├── data-model.md                    # Phase 1 — corpus, chunk, index, questions, runs, labels
├── quickstart.md                    # Phase 1 — the runnable 8-day path, with the cut order
├── contracts/
│   ├── foundry-redeployment.md      # US3: the two debts, pre-flight to measurement
│   ├── search-service-and-index.md  # US2: the free service, RBAC, the envelope
│   └── retrieval-and-scoring.md     # US1: four methods, pooled labels, the metrics
├── checklists/
│   └── requirements.md              # Spec quality checklist (complete)
├── findings.md                      # Written during implementation, block 4's format
└── tasks.md                         # Created by /speckit-tasks, not by this command
```

### Source code (repository root)

```text
infra/
├── main.bicep                       # Unchanged — northeurope, classical ML. NOT deployed here
├── ci-identity.bicep                # Unchanged — Microsoft.Search deliberately absent
├── foundry.bicep                    # MODIFIED — two changes, both in contracts/foundry-redeployment.md
│                                    #   1. Foundry User by GUID, replacing Cognitive Services OpenAI User
│                                    #   2. text-embedding-3-large (Standard), CHAINED into the F1 sequence
└── search.bicep                     # NEW — Free tier, semanticSearch 'free', disableLocalAuth,
                                     #   two caller role grants by GUID

genaiops/foundry-block3/             # Unchanged — call_model.py reused as the SC-007 probe
qa-observability/foundry-block4/     # Unchanged — read for its findings, not modified

rag-optimization/
└── rag-block5/                      # NEW — this feature
    ├── README.md                    # Author's first-person account; both case studies
    ├── pyproject.toml               # uv, pins from research.md § R10
    ├── chunk_corpus.py              # tiktoken distribution FIRST, then H2-aware 512/128 chunking
    ├── create_index.py              # data-plane index: vector profile + semantic configuration
    ├── embed_and_push.py            # local embedding, push over the data plane, no key
    ├── service_stats.py             # /servicestats and /indexes/*/stats — SC-005, SC-006
    ├── run_retrieval.py             # --method keyword|vector|hybrid|hybrid_semantic
    ├── pool_for_labelling.py        # union of the four runs, ready to label
    ├── score_retrieval.py           # DocumentRetrievalEvaluator, explicit 0..3 range
    ├── questions/
    │   ├── questions.jsonl          # COMMITTED — ~20, one unanswerable control
    │   └── labels.jsonl             # COMMITTED — the only artifact no command regenerates
    ├── runs/                        # NOT committed — regenerable from the index
    └── results/
        └── comparison.md            # COMMITTED — the deliverable table
```

**Structure Decision**: the workload occupies `rag-optimization/`, the folder the
constitution's structure table reserves for it and the last one still empty —
continuing the one-topic-folder-per-block split that `genaiops/` and
`qa-observability/` already follow.

IaC is split deliberately across two templates rather than one. `foundry.bicep`
is modified in place because User Story 3 *is* the settlement of a debt in that
specific file, and its hard-won re-runnability has to be re-proved after the
edit; folding a new resource type into it would make "the second deployment
still works" an ambiguous claim about which change was being tested.
`search.bicep` is therefore separate, and separately deployed twice.

The commit split follows the same seam: template changes, workload code, question
set and results are four logical changes, not one.

## Complexity Tracking

*No entries — Constitution Check reported no violations.*
