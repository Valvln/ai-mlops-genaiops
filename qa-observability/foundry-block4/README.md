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
| Cost of the build day (2026-08-23) | **0.00752 EUR**, measured — all of it `Foundry Models` |
| Log Analytics, same day | **0.0 EUR** — a displayed zero, not an absent row |
| At-rest cost of an idle day | **not measured** — see below |

## What is not proven

**Span delivery was unreliable, and it was my dependency's fault after all.**
For two days I had this filed as a service-side loss: the exporter got HTTP 200
and per-item acceptance, the tracer provider was never replaced, the component
reported no sampling and no cap, and it reproduced on a fresh workspace and on
block 3's untouched script. Every layer I owned came back innocent, so I closed
it as something Application Insights was doing to me.

It was not. `configure_azure_monitor()` installs a sampler even when you never
ask for one, and in `azure-monitor-opentelemetry` 1.8.6 the default became
`RateLimitedSampler` at 5 traces/second. Its percentage starts at **zero** and
needs about half a second of process life to reach 100%, so a CLI that
configures, calls and exits is the worst case it has. The spans were dropped
before the exporter ever saw them — which is also why `force_flush()` was
telling the truth. There was nothing queued to flush.

The lesson I actually take is not about sampling. When I checked
`samplingPercentage: null` on the component I believed I had ruled sampling out.
That field covers **ingestion** sampling, on the resource. The SDK samples
first, in my process, and I never looked there. The test was clean and answered
a question next to the one I was asking. That is the constitution's 1.1.0 rule —
read the source next to the measurement — catching a finding written before the
rule existed.

Fixed with `sampling_ratio=1.0` in `evaluate_call.py` and in block 3's
`call_model.py`, verified offline: 1 span in 12 recorded before, 12 in 12 after.
`specs/007-genai-eval-observability/findings.md` § F6 has the full trail,
including the wrong conclusion and the evidence that supported it.

**What is still not proven is the round trip.** The fix is measured against the
installed package, not against Azure — I tore the environment down and this
audit created nothing. The retrieval of two specific records (the prompt
comparison, the fixture's verdict) stays undemonstrated until there is an
environment to re-run them in. The rule the loss taught still stands, and stands
better now: a flush returning true, an `HTTP 200` and `Items accepted` are three
acknowledgements, and none of them is "queryable". A record counts as
retrievable when a *separate process reads it back*.

**Verified against Azure, 2026-09-24.** I redeployed the environment and ran 24
probe processes, alternating the two configurations. With the default sampler,
3 spans of 12 arrived in Log Analytics, and they were exactly the 3 the process
had recorded. With `sampling_ratio=1.0`, 12 of 12 arrived. The real scripts
delivered 8 spans of 8. The prompt comparison and the fixture's `fail` verdict
were both read back by a separate process. The same run found F9: a judge call
that fails still exports a span with no score, and the readers count it as an
evaluation.

**The at-rest cost of an idle day is a prediction, not a measurement, and I want
that written down rather than rounded off.** Cost Management, read on
2026-08-25, gives `rg-ai300-foundry` **0.00752 EUR on 2026-08-23** — the only
day this environment existed, and a day with ~13 model calls in it. Broken down
by meter, **all of it is `Foundry Models`**; `Log Analytics` shows **0.0**, a
displayed zero rather than an absent row, so the whole session's telemetry
ingested for nothing.

What is missing is the other half: a day where the *token* cost is zero too.
That day never happened, because I deployed and destroyed inside the same one.
For 2026-08-24 there is no row for this group *and none for any other group*,
and with the subscription now empty there is no control billing that day to
prove the data landed — so that absence is "no data yet", not a confirmed zero.
I expect €0.00; I have not seen it.

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
