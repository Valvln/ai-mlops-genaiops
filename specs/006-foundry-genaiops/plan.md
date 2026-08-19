# Implementation Plan: Block 3 — Azure AI Foundry GenAIOps backbone

**Branch**: `006-foundry-genaiops` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-foundry-genaiops/spec.md`

## Summary

Deploy the smallest Azure AI Foundry footprint that exercises Domain 3's three
core objectives — a token-billed model deployment, a prompt versioned as a git
file, and a call whose trace is retrievable after the fact — in a new,
independently-destroyable resource group in `swedencentral`.

The technical approach is shaped by three findings from this session's
research, not by the cost model's original assumptions:

- **The cost model's recommended model, `gpt-5-nano`, is blocked by quota, not
  by capability.** A live `what-if` failed with `InsufficientQuota`; this
  subscription's quota for `OpenAI.GlobalStandard.gpt-5-nano` is `0`. The
  catalog says a SKU exists; only quota says a subscription can use it.
  `gpt-4.1-mini` (`GlobalStandard`, capacity 1) replaces it — real quota,
  not deprecated, and what-if'd clean alongside the account and project in one
  probe ([research.md § R4](./research.md)).
- **Tracing is Application Insights, connected to the Foundry project — there
  is no Foundry-native trace store.** Confirmed against Microsoft Learn,
  current as of 2026-08-06. Retrieval after the fact (this feature's whole
  point for User Story 3) means querying that connected resource, not
  re-reading portal state ([research.md § R6](./research.md)).
- **Prompt versioning is a plain `.prompty` file in git, not Prompt Flow.**
  Prompt Flow is scheduled for retirement (2027-04-20) and isn't recommended
  for new work; a git-tracked file satisfies FR-006 without depending on it
  ([research.md § R7](./research.md)).

## Technical Context

**Language/Version**: Bicep (IaC); Python 3.11 for the call/trace harness,
`uv`-managed, matching `mlops/training-pipeline`'s convention

**Primary Dependencies**: `prompty` (loads `.prompty` files), `openai` SDK
(the Foundry deployment's endpoint is OpenAI-API-compatible), `azure-identity`
(Entra auth to the deployment — no API keys), `opentelemetry-sdk` +
`azure-core-tracing-opentelemetry` (call-side spans exported to the connected
Application Insights resource, per [research.md § R6](./research.md))

**Storage**: N/A for application state. The trace store is Application
Insights / its underlying Log Analytics workspace — Azure-managed, not this
feature's schema to define (see [data-model.md](./data-model.md))

**Testing**: verification by observation, the same pattern feature 005 used —
`call_model.py` sends a call, `query_trace.py` retrieves its trace in a
**separate invocation**, and the retrieved record is compared against what was
actually sent. There is no unit-test suite; the retrieval *is* the test
([contracts/call-and-trace.md](./contracts/call-and-trace.md))

**Target Platform**: Azure AI Foundry (account + project) in `swedencentral`;
harness runs locally (macOS, `uv`)

**Project Type**: GenAI operationalization workload — IaC under `infra/`,
workload scripts under `genaiops/`, mirroring the `infra/` + `mlops/` split
feature 005 established for classical ML

**Performance Goals**: none — throughput isn't the point, same posture feature
005 took for training time

**Constraints**: €0.00 at rest for every resource this feature creates (spec
Cost section); the true gating constraint turned out to be **quota**, not
price — `gpt-5-nano`'s zero quota in `swedencentral` is the binding limit
([research.md § R4](./research.md)), not the €1.14 budget ceiling the cost
model priced; no CI role change, no gated deployment ([research.md §
R8](./research.md))

**Scale/Scope**: one Foundry account, one project, one model deployment, one
Application Insights + Log Analytics pair, one or two `.prompty` files, a
handful of test calls (well under 20)

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this plan satisfies it |
| --- | --- | --- |
| **I. Cost discipline** (non-negotiable) | ✅ Pass | Every resource checked against "does it bill at rest" before being proposed (spec Cost section, restated in [contracts/foundry-deployment.md](./contracts/foundry-deployment.md)). Region and model chosen only after live `what-if`/quota checks, not from the cost model's dated snapshot — R4 caught a model the snapshot recommended that this subscription cannot actually deploy. Cheapest viable form throughout: `GlobalStandard` over `Standard` where both had quota, no hub, no AI Search, App Insights ingestion sized for a handful of calls |
| **II. Version control hygiene** | ✅ Pass | `infra/*.json` build outputs stay gitignored, matching `main.bicep`'s pattern. Every API version in this plan was verified against the live subscription this session (`what-if`) or flagged as **not yet verified** where it wasn't (R3, R6) — none is copied from an example of unknown age without that flag |
| **III. Commit authorization** (non-negotiable) | ✅ Pass | No commit or push performed by this plan. Tasks will end in proposed commits, one logical change each, for the author to run |
| **IV. Documentation ownership** | ✅ Pass | `README.md` updated at the milestone in the author's first person, drafted for review, not committed by this plan |
| **V. Validation before commit** | ✅ Pass | `az bicep build` + `az deployment group what-if` required before any deployment is proposed ([contracts/foundry-deployment.md](./contracts/foundry-deployment.md)). The `connections` resource (R3, R6) is explicitly flagged as not yet validated — it will be, before it's proposed, not assumed clean because a public sample uses it |
| **VI. English only** | ✅ Pass | All artifacts in English |
| **VII. Folder structure** | ✅ Pass | IaC in `infra/` (new file, `foundry.bicep`, not merged into `main.bicep`); workload in `genaiops/`, the folder this repository's layout table already reserves for generative AI operationalization and which has been empty until now |

**Additional gates this repository has earned:**

| Gate | Status | Notes |
| --- | --- | --- |
| Never approve the deployment gate on the author's behalf | ✅ | No gated deployment — this feature deploys manually, outside CI ([research.md § R8](./research.md)) |
| Never widen the CI role with a built-in role | ✅ | CI role untouched; FR-012 is dormant unless this default is revisited |
| Read the captured error, not the green summary | ✅ | This plan's central finding (R4) came from reading `InsufficientQuota` and `ServiceModelDeprecated` messages directly rather than trusting a clean-looking model catalog listing |
| A criterion that passes is not an objective met | ✅ | SC-004 requires trace retrieval from a *separate invocation*, not the same process that made the call — the contract makes this explicit rather than implicit |
| Deferred criteria declared in advance | ✅ | SC-006 (at-rest cost), same 8–24h Cost Management lag feature 005 documented |

**Result: no violations. Complexity Tracking is therefore omitted.**

### Re-evaluation after Phase 1 design

- **Principle V's scope widened, not narrowed.** Phase 0 research surfaced a
  second thing that needs `what-if` validation before deployment — the
  `connections` resource for tracing — that wasn't visible from the spec
  alone. This is now explicit in the contract rather than an assumption
  carried into implementation.
- **Principle I is satisfied by a different mechanism than the spec assumed.**
  The spec worried about billing rate; the actual blocker this research found
  was quota (a hard zero, not a price). Both are "does it stop before it
  starts" questions, so the principle's spirit is intact, but the plan now
  documents quota as a first-class pre-deployment check
  ([contracts/foundry-deployment.md](./contracts/foundry-deployment.md) § 1),
  not just a price check.
- **No new violations.** The gate passes after design as it did before.

## Project Structure

### Documentation (this feature)

```text
specs/006-foundry-genaiops/
├── plan.md                      # This file
├── spec.md                      # Feature specification
├── research.md                  # Phase 0 output — decisions, live-verified
├── data-model.md                # Phase 1 output — Azure + repo entities
├── quickstart.md                # Phase 1 output — the runnable validation path
├── contracts/
│   ├── foundry-deployment.md    # What infra/foundry.bicep must (not) create
│   └── call-and-trace.md        # What the harness scripts must guarantee
├── checklists/
│   └── requirements.md          # Spec quality checklist (complete)
└── tasks.md                     # Created by /speckit-tasks, not by this command
```

### Source code (repository root)

```text
infra/
├── main.bicep                   # Unchanged — northeurope, classical ML
├── ci-identity.bicep            # Unchanged — no CI role change (R8)
└── foundry.bicep                # New — this feature, swedencentral,
                                  # deployed manually (R8), never by CI

genaiops/
└── foundry-block3/              # New — this feature
    ├── README.md                # What was built, observed values
    ├── pyproject.toml           # Pinned local environment (uv)
    ├── prompts/
    │   └── hello-domain3.prompty
    ├── call_model.py            # Sends one call, emits an OTel span
    └── query_trace.py           # Retrieves a trace, separate invocation
```

**Structure Decision**: IaC and workload code follow the split feature 005
established (`infra/` for Bicep, a topic folder for the workload) rather than
inventing a new layout. `infra/foundry.bicep` is a sibling of `main.bicep`,
not a module included by it — the two are deployed independently, to
different resource groups, on different schedules, which is the point of
[research.md § R5](./research.md)'s resource-group decision.

## Complexity Tracking

*No entries — Constitution Check reported no violations.*
