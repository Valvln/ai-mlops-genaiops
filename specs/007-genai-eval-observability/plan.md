# Implementation Plan: Block 4 — GenAI QA and Observability

**Branch**: `007-genai-eval-observability` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-genai-eval-observability/spec.md`

## Summary

Redeploy `infra/foundry.bicep` — unchanged — into a fresh `rg-ai300-foundry`, then add a
local evaluation harness on top of block 3's existing call-and-trace mechanism: one
groundedness check and one general quality check, run with the Azure AI Evaluation SDK
against the same `gpt-4.1-mini` deployment that already answers calls, with results
emitted as a second span type (`genaiops.eval`) into the same Application Insights
resource block 3 already deployed, retrievable in a separate invocation and joinable back
to the call it scored.

Two findings from this session's research shape the approach more than the spec's own
assumptions did:

- **The redeploy target is presently soft-delete-locked.** Feature 006's own teardown
  record (`specs/006-foundry-genaiops/tasks.md`, T028) names the exact soft-deleted
  account (`ai300fdrylkcq74thutjeq`, held until `2026-08-24T00:17:31Z`) that
  `uniqueString(resourceGroup().id)` will reproduce if `rg-ai300-foundry` is recreated
  under its existing name before that date. `infra/foundry.bicep` does not change; a
  purge step runs before the redeploy ([research.md § R1](./research.md)).
- **Cloud/portal evaluation would pull in a resource this feature doesn't need.**
  Logging evaluation results into the Foundry project's own portal view requires a
  connected storage account — the same shape of avoidable dependency block 3 already
  declined once, for tracing discovery. Evaluating locally with the SDK's evaluator
  classes and writing results into the already-deployed Application Insights resource
  (the same mechanism `call_model.py` uses) satisfies FR-004/SC-002 without it
  ([research.md § R2](./research.md)).

## Technical Context

**Language/Version**: Bicep (IaC, unchanged — `infra/foundry.bicep` is redeployed
as-is); Python 3.11 for the evaluation harness, `uv`-managed, matching
`genaiops/foundry-block3`'s convention

**Primary Dependencies**: `azure-ai-evaluation>=1.18,<2` (`GroundednessEvaluator`,
`RelevanceEvaluator`), `openai` SDK and `azure-identity` (reused from
`genaiops/foundry-block3` — same deployment, same Entra ID credential),
`opentelemetry-sdk` + `azure-core-tracing-opentelemetry` (evaluation-side spans,
exported to the same connected Application Insights resource block 3 deployed)

**Storage**: N/A for application state. Evaluation results are spans in the same
Application Insights / Log Analytics workspace block 3 already created — no new trace
store, and explicitly no Foundry-project-connected storage account (research.md § R2)

**Testing**: verification by observation, extending block 3's pattern —
`evaluate_call.py` scores a call's response and emits a `genaiops.eval` span;
`query_evaluations.py` retrieves it in a **separate invocation** and joins it back to the
`genaiops.call` record it scored. There is no unit-test suite; the retrieval is the test
([contracts/evaluate-and-retrieve.md](./contracts/evaluate-and-retrieve.md))

**Target Platform**: Azure AI Foundry (account + project + one model deployment, all
unchanged from `infra/foundry.bicep`) in `swedencentral`; harness runs locally (macOS,
`uv`)

**Project Type**: QA/observability workload, sitting on top of the GenAIOps workload
feature 006 built — code lives under `qa-observability/`, the repository's
reserved-and-until-now-empty folder for this exact scope, not under `genaiops/`
([research.md § R6](./research.md))

**Performance Goals**: none — as in block 3, throughput isn't the point

**Constraints**: €0.00 at rest for every resource this feature creates or reuses (spec
Cost section); total model invocations across the whole verification ≤ 500 (SC-006);
evaluator judge calls authenticate with Entra ID only, matching the account's
`disableLocalAuth: true` (research.md § R3); no second model deployment (research.md §
R5); no CI role change, no gated deployment — same manual-deployment posture spec 006
already established and this feature inherits without reopening it

**Scale/Scope**: one redeployed Foundry account/project/deployment (identical to block
3's), one new prompt file (`grounded-qa.prompty`) iterated across two revisions, two
evaluators (`GroundednessEvaluator`, `RelevanceEvaluator`), a handful of live calls plus a
handful of evaluator calls — expected well under 30 total invocations against SC-006's
500-invocation ceiling ([research.md](./research.md), cost re-derivation)

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this plan satisfies it |
| --- | --- | --- |
| **I. Cost discipline** (non-negotiable) | ✅ Pass | Every resource this feature touches was already checked against "does it bill at rest" in the spec's Cost section, and this plan adds none beyond it — no storage account, no second deployment, no hub (research.md § R2, § R5). SC-006's invocation cap is the mechanism that keeps the one genuinely variable cost (evaluator judge calls) bounded, sized against a realistic worst case rather than assumed small (research.md, cost re-derivation) |
| **II. Version control hygiene** | ✅ Pass | `infra/*.json` build outputs stay gitignored, unchanged from block 3's pattern. The one new dependency (`azure-ai-evaluation`) is pinned to a version verified against PyPI this session, not copied from memory (research.md, package pin). `infra/foundry.bicep` itself is redeployed unchanged — no new API version claims to verify beyond what feature 006 already validated |
| **III. Commit authorization** (non-negotiable) | ✅ Pass | No commit or push performed by this plan. The one mutating Azure action this plan identifies as necessary before implementation (purging the soft-deleted account, research.md § R1) is flagged as author-authorized at implementation time, not something this plan or a future task performs unattended |
| **IV. Documentation ownership** | ✅ Pass | `qa-observability/foundry-block4/README.md` will be drafted at the milestone in the author's first person, for review, not committed by this plan |
| **V. Validation before commit** | ✅ Pass | `az bicep build` (trivially, since the file is unchanged) plus `az deployment group what-if` required before the redeploy, exactly as spec 006 required for the original deployment. Quota for `gpt-4.1-mini` is re-verified live at implementation time rather than trusted from feature 006's session, mirroring that feature's own R4 (research.md § R5) |
| **VI. English only** | ✅ Pass | All artifacts in English |
| **VII. Folder structure** | ✅ Pass | This feature is `qa-observability/`'s first occupant — the folder the repository layout table already reserves for "Quality assurance, monitoring, observability," distinct from `genaiops/`'s scope (research.md § R6). No new top-level folder proposed |

**Additional gates this repository has earned:**

| Gate | Status | Notes |
| --- | --- | --- |
| Never approve the deployment gate on the author's behalf | ✅ | No gated deployment — manual, outside CI, same as block 3 |
| Never widen the CI role with a built-in role | ✅ | CI role untouched; this feature doesn't touch `infra/ci-identity.bicep` at all |
| Read the captured error, not the green summary | ✅ | R5 treats `gpt-4.1-mini`'s suitability as a judge model as unverified rather than assumed, with a named fallback and an explicit check (the first evaluator call's parsed output) rather than a hope |
| A criterion that passes is not an objective met | ✅ | FR-008 requires an evaluation's absence to be distinguishable from a zero score — carried into the contract explicitly (contracts/evaluate-and-retrieve.md), not left implicit |
| Deferred criteria declared in advance | ✅ | SC-008 (at-rest cost), same Cost Management ingestion lag block 3 and block 2 both documented |
| The Key-Vault-shaped trap, recognized on sight | ✅ | R1 is this repository's second encounter with a soft-delete-locked resource name blocking a redeploy — recognized from `infra/DEPLOY.md`'s Key Vault precedent and resolved the same way (purge, not rename) rather than rediscovered from scratch |

**Result: no violations. Complexity Tracking is therefore omitted.**

### Re-evaluation after Phase 1 design

- **Principle I's scope was already tight; Phase 1 didn't widen it.** The data model and
  contracts add no resource beyond what Technical Context already named — evaluation
  results are spans, not a new Azure resource type.
- **Principle V gained one more explicit pre-check.** The evaluate-and-retrieve contract
  now states plainly that the first evaluator call against `gpt-4.1-mini` is itself the
  validation of R5's judge-model choice, not a separate step to remember later.
- **No new violations.** The gate passes after design as it did before.

## Project Structure

### Documentation (this feature)

```text
specs/007-genai-eval-observability/
├── plan.md                        # This file
├── spec.md                        # Feature specification
├── research.md                    # Phase 0 output — decisions, live-verified
├── data-model.md                  # Phase 1 output — trace + evaluation entities
├── quickstart.md                  # Phase 1 output — the runnable validation path
├── contracts/
│   ├── foundry-redeployment.md    # Pre-flight, redeploy, and re-verification steps
│   └── evaluate-and-retrieve.md   # What the eval harness scripts must guarantee
├── checklists/
│   └── requirements.md            # Spec quality checklist (complete)
└── tasks.md                       # Created by /speckit-tasks, not by this command
```

### Source code (repository root)

```text
infra/
├── main.bicep                     # Unchanged — northeurope, classical ML
├── ci-identity.bicep               # Unchanged — no CI role change
└── foundry.bicep                  # Unchanged — redeployed as-is (R1)

genaiops/
└── foundry-block3/                # Unchanged — read from, not written to
    ├── call_model.py              # Reused to produce the calls this feature scores
    └── query_trace.py             # Reused to confirm a call's own trace still resolves

qa-observability/
└── foundry-block4/                # New — this feature
    ├── README.md                  # What was built, observed values
    ├── pyproject.toml             # Pinned local environment (uv), azure-ai-evaluation
    ├── prompts/
    │   └── grounded-qa.prompty    # New — iterated across ≥2 revisions (research.md § R8)
    ├── fixtures/
    │   └── unsupported_claim.json # The hand-authored failing-groundedness case (R7)
    ├── evaluate_call.py           # Scores a call's response, emits a genaiops.eval span
    └── query_evaluations.py       # Retrieves eval results, joined back to their call
```

**Structure Decision**: IaC stays untouched, redeployed rather than modified
([research.md § R1](./research.md)). The workload code follows the topic-folder split
this repository already established (`genaiops/` for feature 006, now `qa-observability/`
for this one), rather than extending `genaiops/foundry-block3/` in place — the two
folders' scopes are distinct per the repository layout table, and this feature is the
first to occupy the one reserved for it ([research.md § R6](./research.md)).

## Complexity Tracking

*No entries — Constitution Check reported no violations.*
