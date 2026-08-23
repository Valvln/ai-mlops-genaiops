# Block 4 — GenAI QA and Observability

AI-300 Domain 4, built on block 3's call-and-trace foundation. Block 3 proved a
call could be retrieved after the fact. This block asks the same question one
level up: can the **judgement** about a call be retrieved after the fact?

*Draft — Claude wrote this from the session's observed values, for me to
rewrite and commit.*

## What this does

```bash
# Score a real call block 3 already made:
uv run evaluate_call.py --trace-id <id> --metric relevance

# Score a hand-authored failing case, no live call:
uv run evaluate_call.py --fixture fixtures/unsupported_claim.json --metric groundedness

# Read the verdict back, in a separate invocation:
uv run query_evaluations.py --trace-id <id>
uv run query_evaluations.py --compare <version-a> <version-b> --metric groundedness
uv run query_evaluations.py --count-invocations --since 1d
```

`evaluate_call.py` writes a `genaiops.eval` span; `query_evaluations.py` reads
it back from Log Analytics. They are separate programs on purpose, exactly as
`call_model.py` and `query_trace.py` are — a query that shares a process with
the thing it is "retrieving" answers an easier question than the one being
asked.

## The five things learned

### 1. An LLM judge has two independently wrong things, and only one is the model's

The fixture answers correctly and then invents a 40% idle discount, 60-second
billing increments, and a 500,000-token free allowance. At the SDK's default
threshold of 3 it scored **4.0 — `pass`**. The judge's reasoning was *perfect*:
it named all three inventions as unsupported. The verdict was still wrong,
because a 1–5 score averages fabrications against the parts that were right.
At threshold 5, the same score and the same reasoning give `fail`.

A groundedness gate at threshold 3 asks "is this mostly grounded", which a
confident fabrication passes. 
Takeaway: when an evaluation gate misfires, check the threshold before blaming the judge.

### 2. `capacity: 1` is one request per minute, not just 1000 tokens per minute

Block 3 never noticed, because its calls were manual and minutes apart. Block 4
scores a response by calling a judge, so every scored answer is at least two
calls, and it 429'd immediately.

Raising capacity to 10 costs nothing. On a per-token SKU capacity is a
*throttle*; on a provisioned one the same number would be a billing floor.

### 3. `az bicep build` could not see either template defect

`infra/foundry.bicep` had two, and this block found both by deploying:

- **A race.** Every child of a Cognitive Services account mutates the account,
  and Azure rejects whichever loses. My first fix ordered the project against
  the connection — and the project then raced the *deployment* instead. All four children are now
  chained.
- **A name collision.** Both App Insights connections were declared with the
  same name, and a project shares the account's connection namespace, so the
  second collided with the first. Feature 006 never saw it because the race
  happened to order them the other way.

The template now deploys clean and, **twice**.

### 4. Deleting the resource group did not delete the workspace

The redeploy reported success and four resources. The Log Analytics workspace
reported `createdDate: 2026-08-19` — feature 006's date. `az group delete` had
only *soft-deleted* it, and recreating restored it, with four days of old spans.

This is a second soft-delete trap. A workspace inside its recovery window is restored **silently and reported as a successful create** — so "the template recreated what it describes" and "the template restored what was already there" are indistinguishable unless you read `createdDate`. Teardown now uses `--force`.

### 5. A cost guardrail that reads a lossy store fails toward under-reporting

`--count-invocations` deliberately counts spans in the trace store rather than
keeping a tally alongside, because a second source of truth drifts. Roughly 70% of this session's spans never reached the workspace despite the exporter receiving `HTTP 200` and an explicit `Items accepted: 8` — so the counter reported **3** invocations for a session that made about **13**.

It failed in the flattering direction. A budget check that silently reads low
is worse than no budget check.

## Observed values

| | |
| --- | --- |
| Region / SKU | `swedencentral`, `GlobalStandard`, capacity 10 |
| Judge model | `gpt-4.1-mini` — same deployment being evaluated |
| Relevance, a good answer | 5.0 / threshold 3 → `pass` |
| Groundedness, a grounded answer | 5.0 / threshold 5 → `pass` |
| Groundedness, the fixture | 4.0 / threshold 5 → `fail` |
| Invocations | ~13 actual, against SC-006's cap of 500 |
| At-rest cost | €0.00 — nothing here bills while idle |

## What is not proven

**Span delivery is unreliable, and it is not this code's fault.** The exporter
gets HTTP 200 and per-item acceptance; the tracer provider is never replaced;
no sampling or cap is configured; it reproduces on a workspace minutes old and
on block 3's unmodified script. Roughly 70% of spans still never appear.

So the retrieval of two specific records — the prompt comparison and the
fixture's verdict — could not be demonstrated, though both evaluations ran
correctly and repeatedly. `specs/007-genai-eval-observability/findings.md` § F6
has the full evidence and the one untested hypothesis left: service-driven
adaptive sampling, which the SDK is observably fetching configuration for.

## Teardown

Nothing here bills at rest, but the environment is disposable by design:

```bash
az monitor log-analytics workspace delete -g rg-ai300-foundry \
  -n <workspace> --force true --yes      # --force, or it comes back (§ 4)
az group delete --name rg-ai300-foundry --yes
az cognitiveservices account purge -g rg-ai300-foundry -n <account> -l swedencentral
```

The purge is not optional if the group will be rebuilt within 48 hours: the
account name derives from `uniqueString(resourceGroup().id)`, so the same name
recurs and collides with the soft-delete registry.
