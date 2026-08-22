# Data Model: Block 4 — GenAI QA and Observability

Two kinds of entity: what `infra/foundry.bicep` provisions (unchanged from spec 006,
restated here only for reference) and what this feature adds — records in the same
trace store, not a new schema this feature owns end to end.

## Inherited from block 3 (unchanged)

| Entity | What it is | Source of truth |
| --- | --- | --- |
| Foundry account, Foundry project, model deployment | The redeployed Azure resources this feature calls and evaluates against | `infra/foundry.bicep`, unchanged |
| Call trace (`genaiops.call` span) | One request to the model deployment: prompt file, prompt version (git revision, `-dirty` suffix if uncommitted), deployment name, response content, token usage | Application Insights / Log Analytics, written by `call_model.py` |

## New: Evaluation record (`genaiops.eval` span)

One evaluator invocation against one response, whether that response came from a live
call this session made or from a hand-authored fixture (research.md § R7). Emitted by
`evaluate_call.py`, read back by `query_evaluations.py`.

| Attribute | Type | Meaning | Set before or after the evaluator call? |
| --- | --- | --- | --- |
| `eval.metric` | string | Which evaluator produced this record — `"groundedness"` or `"relevance"`, matching the SDK's own keyword mapping | before — known from which evaluator is being run |
| `eval.evaluated_trace_id` | string | The `genaiops.call` span's trace id this record scores, or the literal string `"fixture"` for a hand-authored case not backed by a live call | before |
| `prompt.version` | string | Copied from the scored call's own `prompt.version` attribute (or the evaluated prompt file's own git revision, for the fixture case) — reuses the existing attribute name rather than inventing a parallel identifier (FR-004) | before |
| `gen_ai.request.model` | string | The deployment that produced the response being scored (`gpt-4.1-mini`) | before |
| `eval.judge_model` | string | The deployment used as the evaluator's own judge (`gpt-4.1-mini` in this feature's design — research.md § R5) | before |
| `eval.score` | double | The evaluator's numeric score (e.g. groundedness 1–5) | after — comes from the evaluator's return value |
| `eval.threshold` | double | The evaluator's own pass/fail threshold (e.g. `groundedness_threshold`) | after |
| `eval.result` | string | `"pass"` or `"fail"`, read from the evaluator's own `*_result` field — not recomputed from `eval.score`/`eval.threshold` independently, so the record always agrees with what the evaluator itself concluded | after |
| `eval.reason` | string | The evaluator's own chain-of-thought explanation (`*_reason` field), recorded for the same transparency reason `call_model.py` records full response content | after |

**Absence is not a record.** A call with no evaluation run against it has no
`genaiops.eval` span naming its trace id — `query_evaluations.py` reports this as "no
evaluation found," never as a row with `eval.score = 0` (FR-008).

## New: Prompt comparison (derived, not stored)

Not a stored entity — a query-time pairing of two Evaluation records that share
`eval.metric` but differ in `prompt.version`, both scored against the same test question.
`query_evaluations.py`'s comparison mode retrieves both and states which `prompt.version`
scored higher on which metric (SC-004); nothing is written back to the trace store to
represent the comparison itself.

## New: Groundedness fixture

A committed JSON file (`fixtures/unsupported_claim.json`) under
`qa-observability/foundry-block4/fixtures/`, holding one hand-authored `query`/`context`/
`response` triple where `response` asserts something `context` does not support
(research.md § R7). Not a live call, not a span-producing event on its own — it becomes
one only when `evaluate_call.py` scores it, at which point it produces a
`genaiops.eval` record like any other, with `eval.evaluated_trace_id = "fixture"`.

## Relationships

```text
genaiops.call (block 3)              genaiops.eval (this feature)
┌─────────────────────┐              ┌──────────────────────────┐
│ trace_id             │◄─────────── │ eval.evaluated_trace_id  │
│ prompt.version        │◄─────────── │ prompt.version            │
│ gen_ai.request.model   │◄─────────── │ gen_ai.request.model        │
│ gen_ai.response.content │            │ eval.metric, .score,       │
└─────────────────────┘              │ .threshold, .result, .reason│
                                      └──────────────────────────┘
```

One call may have zero, one, or several evaluation records (one per metric run against
it). A fixture-backed evaluation record has no corresponding `genaiops.call` span at all
— `eval.evaluated_trace_id = "fixture"` is how `query_evaluations.py` recognizes and
labels that case rather than reporting a failed join as if it were missing data.
