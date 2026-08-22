# Contract: scoring a call, and retrieving what it scored

What `evaluate_call.py` and `query_evaluations.py` must guarantee between them, so User
Stories 1–3 are provable rather than asserted — the same role
`specs/006-foundry-genaiops/contracts/call-and-trace.md` played for `call_model.py` and
`query_trace.py`, one layer up.

## `evaluate_call.py`

**Input**: either `--trace-id <id>` (scoring a real call `call_model.py` already made and
flushed) or `--fixture fixtures/unsupported_claim.json` (scoring the hand-authored
failing case, research.md § R7) — mutually exclusive, exactly one required.

**Must do, in order**:

1. Resolve what is being scored:
   - `--trace-id` path: query the same Log Analytics workspace `query_trace.py` already
     reads, for the named trace's `prompt.file`, `prompt.version`,
     `gen_ai.request.model`, and `gen_ai.response.content`. Refuse (exit non-zero) if the
     trace id resolves to nothing — never silently substitute an empty response.
   - `--fixture` path: load the JSON file directly; no Azure query needed to resolve the
     input, only to emit the result.
2. Build the evaluator's `model_config` with **no `api_key`** — Entra ID via
   `DefaultAzureCredential`, matching the account's `disableLocalAuth: true` and
   `call_model.py`'s own credential object (research.md § R3). The judge deployment is
   `gpt-4.1-mini`, the same one being evaluated (research.md § R5).
3. **Attributes known before the evaluator call are set before it**, on the same
   "attribute the attempt, not just the success" principle `call_model.py` already
   follows: `eval.metric`, `eval.evaluated_trace_id`, `prompt.version`,
   `gen_ai.request.model`, `eval.judge_model`.
4. Call the evaluator (`GroundednessEvaluator` or `RelevanceEvaluator`, per which metric
   was requested) with the resolved `query`/`context`/`response`.
5. Set the remaining attributes from the evaluator's return value —
   `eval.score`, `eval.threshold`, `eval.result` (read directly from the evaluator's own
   `*_result` field, never recomputed independently from score and threshold — if the
   SDK's own pass/fail judgment and a hand-rolled comparison ever disagreed, the
   hand-rolled one would be the bug), `eval.reason`.
6. **`force_flush()` the span exporter before exiting**, exactly as `call_model.py`
   already learned the hard way (spec 006's README: a span queued in a batch processor is
   not a span that was exported, and a short-lived CLI process is exactly where that gap
   opens). Print a warning to stderr, don't fail the exit code, if the flush reports
   incomplete — the same posture `call_model.py` takes.

**Must NOT do**: retry silently on an evaluator or authentication failure; substitute a
placeholder score when the judge model's output doesn't parse (this is exactly the
scenario research.md § R5 names as the reason `gpt-4.1-mini`'s judge suitability is
checked rather than assumed — a parse failure here is the check failing, not something to
paper over).

## `query_evaluations.py`

**Input**: a `--trace-id` (retrieve evaluation(s) for one call), or `--compare
<version-a> <version-b> --metric <name>` (retrieve and contrast two prompt revisions).
Run as a **separate invocation** from `evaluate_call.py`, for the same reason
`query_trace.py` is run separately from `call_model.py` — retrieval proven, not assumed.

**Must do**:

1. Query `genaiops.eval` spans (same table, same pattern as `query_trace.py`'s
   `genaiops.call` query) and, for the `--trace-id` mode, join by
   `eval.evaluated_trace_id` to the corresponding `genaiops.call` record — printing the
   prompt version, deployment identity, and score together (User Story 1, Scenario 2).
2. If no `genaiops.eval` span names the requested trace id, print that plainly — **never**
   a row with a zero or blank score standing in for "not evaluated" (FR-008). This is
   checked, not assumed: the acceptance test for User Story 1's Scenario 3 is running
   this query against a real call that was deliberately never scored, and confirming the
   output says so in words, not in a numeric placeholder.
3. For `--compare`, retrieve both revisions' evaluation records for the named metric and
   state directly which `prompt.version` scored higher — the comparison is printed as a
   conclusion (SC-004: "the direction... is stated, not left for the reader to infer"),
   not as two bare numbers side by side.

## Acceptance mapping

| Scenario | Script(s) | Proves |
| --- | --- | --- |
| User Story 1, Scenario 1–2 (a response gets a retrievable score) | `call_model.py` → `evaluate_call.py --trace-id` → `query_evaluations.py --trace-id`, separate session | SC-002 |
| User Story 1, Scenario 3 (absence ≠ a zero score) | `query_evaluations.py --trace-id` against an unscored call | FR-008 |
| User Story 2 (two prompt revisions compared) | `call_model.py` × 2 (against `grounded-qa.prompty`'s two revisions) → `evaluate_call.py` × 2 → `query_evaluations.py --compare` | SC-004, SC-005 |
| User Story 3, Scenario 1 (grounded response passes) | `call_model.py` → `evaluate_call.py --trace-id`, metric `groundedness` | SC-003 (pass case) |
| User Story 3, Scenario 2 (unsupported claim fails) | `evaluate_call.py --fixture fixtures/unsupported_claim.json` | SC-003 (fail case) |

## Invocation accounting (SC-006)

Every `evaluate_call.py` run against `--trace-id` makes exactly one model call (the
judge); the `--fixture` path makes exactly one as well. `query_evaluations.py` makes
none — it only reads. The total invocation count for SC-006 is therefore: one
`call_model.py` run per scored live call, plus one `evaluate_call.py` run per metric
scored (live or fixture) — a count derivable directly from how many `genaiops.call` and
`genaiops.eval` spans exist in the window, which is what SC-006 requires it be checked
against (the records themselves, not a side tally).
