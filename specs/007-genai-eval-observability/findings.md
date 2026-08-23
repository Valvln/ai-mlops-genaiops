# Findings: what the first real run of Block 4 turned up

Recorded 2026-08-23, during the implementation session that redeployed
`infra/foundry.bicep` and ran the first evaluations against it. Everything here
was **measured, not reasoned about** — each entry carries the command and the
output that produced it.

Five of these are defects in things this feature's plan assumed were already
sound. That is the point of writing them down separately from `research.md`:
research recorded what was decided **before** building, and these are what
building disproved.

**Status: all open.** F1–F3 are `infra/foundry.bicep` changes, deliberately not
made in this session — the plan says the template ships unchanged, and altering
it is a scope decision for the author, not a side effect of debugging. F6 is
unresolved and blocks this feature's central claim.

---

## F1 — `infra/foundry.bicep` has a deployment race, and feature 006 passed on luck

**Severity**: the deployment fails outright, roughly half the time.

The first `az deployment group create` failed:

```text
RequestConflict: Another operation is in progress on the resource
'.../Microsoft.CognitiveServices/accounts/ai300fdrylkcq74thutjeq'.
```

`az deployment operation group list` narrowed it to exactly one resource:

| Resource | State |
| --- | --- |
| `accounts/projects/block3-genaiops` | **Failed — RequestConflict** |
| `accounts/deployments/gpt-4.1-mini` | Succeeded |
| `accounts/connections/...-appinsights` | Succeeded |
| everything else | Succeeded |

**Cause**: `accounts/projects` and `accounts/connections` are both children of
the account and both mutate it, but nothing in the template orders them, so ARM
issues them concurrently. Azure serializes writes to a Cognitive Services
account and rejects the loser. Which one loses is a matter of timing.

**Why feature 006 never saw it**: it didn't. The same template deployed cleanly
on 2026-08-19 because the race happened to resolve the other way. A template
that works when the ordering is lucky is not a validated template — this is the
gap between `az bicep build` and a deployment that `CLAUDE.md` already warns
about, showing up in a form neither the build nor `what-if` can see.

**Fix, when authorized**: an explicit `dependsOn` from the project to the
account-level connection (or vice versa) to force serialization.

---

## F2 — `infra/foundry.bicep` cannot be re-run at all

**Severity**: the template is one-shot; it cannot converge.

Re-running the identical deployment to recover from F1 failed differently:

```text
UserError: Connection ai300fdrylkcq74thutjeq-appinsights already exist, and can
only be updated by the workspace that created it, which is the workspace with
workspaceId: .../Microsoft.MachineLearningServices/workspaces/
ai300fdrylkcq74thutjeq@AML
```

The account-level connection refuses to be re-declared. So the template can
create the environment from empty, but it cannot be applied twice — the
ordinary way of recovering from a partial failure is closed, and F1 guarantees
partial failures happen.

Note the identity in the error: `Microsoft.MachineLearningServices/workspaces/...@AML`.
The connection is owned by an AML-workspace projection of the account that the
template never declares and this project deliberately avoids (the "no hub"
constraint). The `2025-04-01-preview` API version on these two connections was
already flagged in feature 006's plan as **not fully pre-verified**. This is
what that flag was worth.

**Fix, when authorized**: make the connections conditional on creation, or drop
them. Worth asking whether they earn their place at all: `call_model.py` reads
the App Insights connection string directly from the component and never
touches these connections, precisely because reading them needs a data action
neither Owner nor `Cognitive Services OpenAI User` carries.

---

## F3 — `capacity: 1` means one request per minute, and that is unusable for Block 4

**Severity**: blocked every evaluation until changed.

The first successful judge call returned:

```text
RateLimitError: Error code: 429 - Your requests to gpt-4.1-mini for
gpt-4.1-mini in swedencentral have exceeded rate limit.
```

`az cognitiveservices account deployment show` gave the reason exactly:

| Limit | Count | Renewal period |
| --- | --- | --- |
| `request` | **1** | 60 s |
| `token` | 1000 | 60 s |

One request per minute. Block 3 never noticed because its calls were manual and
minutes apart. Block 4 is call-plus-judge by construction — at minimum two
model invocations per scored response — so it 429s on contact.

**What was changed, and why it is free**: the live deployment was raised to
`capacity: 10` (10 requests/min, 10,000 tokens/min), verified by re-reading
`properties.rateLimits`. For a token-billed SKU, capacity is a **throttle, not
a reservation**: it sets TPM/RPM and changes neither the per-token price nor
the at-rest cost, which stays €0.00. This is the practical difference between
Standard and Provisioned that `foundry-cost-model.md` § 6 describes — on a
provisioned SKU the same number would be a billing floor.

**Open**: the live deployment now says 10 and `infra/foundry.bicep` still says
1, so template and reality disagree. The template is the source of truth in
this repository, so this drift is a defect until the template is updated.

---

## F4 — `AzureOpenAIModelConfiguration`'s `credential` field cannot be used, and the error blames the wrong thing

**Severity**: cost about half an hour, entirely to a misleading message.

Passing a credential inside the model config — a documented field of the
TypedDict — fails every time:

```text
EvaluationException: (UserError) Model config validation failed.
TypeError: dict contains unknown keys:
  ['credential', 'api_version', 'azure_endpoint', 'azure_deployment']
```

The message names every Azure key as unknown, which reads like a malformed
endpoint. It is not. `validate_model_config` tries
`AzureOpenAIModelConfiguration` first, and the real failure there is:

```text
TypeError: typing.Any cannot be used with isinstance()
```

The field is declared `credential: NotRequired[Any]`, and the SDK validates its
own TypedDicts with `isinstance()`, which cannot accept `Any`. The validator
then falls back to `OpenAIModelConfiguration` and reports **that** attempt's
unknown keys. The surfaced error describes the fallback, not the cause.

**Worked around**: the credential is passed to the evaluator's constructor,
which takes it as a real parameter. Entra ID auth against a `disableLocalAuth`
account works — research.md § R3's decision holds; only the route to it changed.

---

## F5 — The default groundedness threshold passes a confident fabrication

**Severity**: the most consequential finding for what this block is *about*.

`fixtures/unsupported_claim.json` answers correctly and then invents three
things the source does not contain: an automatic 40% idle-time discount,
60-second billing increments, and a 500,000-token free monthly allowance.

At the SDK's default threshold of 3:

```text
score : 4.0 (threshold 3)
result: pass
```

The judge's own reasoning was **correct and complete** — it named all three
inventions as unsupported. The verdict was still `pass`, because a 1–5 score
averages the fabrications against the parts that were right.

This is precisely the failure this repository keeps rediscovering: a check that
runs, reports success, and misses its objective. A groundedness gate at
threshold 3 asks "is this mostly grounded", which a fluent fabrication passes.

At threshold 5, the same score and the same reasoning yield:

```text
score : 4.0 (threshold 5)
result: fail
```

**Resolved in code**: `THRESHOLDS` in `evaluate_call.py` sets groundedness to 5
and leaves relevance at the SDK default of 3, where "mostly on topic" is
genuinely the question. `eval.threshold` is recorded on every span, so a verdict
is always readable against the gate that produced it.

**For the exam notes**: an LLM-as-judge metric has two independently wrong
things — the score and the threshold — and only the first is the model's.

---

## F6 — Evaluation spans are not reaching Log Analytics, and `force_flush` reports success

**Severity**: unresolved, and it blocks SC-002.

Six `genaiops.*` spans were produced. Roughly 40 minutes later, three had
arrived:

| Span | Time | Ingested? |
| --- | --- | --- |
| `genaiops.call` (hello-domain3) | 08:33:37 | yes |
| `genaiops.call` (grounded-qa rev 1) | 08:34:54 | yes |
| `genaiops.eval` relevance | ~08:50 | **no** |
| `genaiops.eval` groundedness, threshold 3 | ~08:53 | **no** |
| `genaiops.eval` groundedness fixture, threshold 3 | ~08:55 | **no** |
| `genaiops.eval` groundedness fixture, threshold 5 | 08:57:12 | yes |
| `genaiops.eval` groundedness rev 1, threshold 5 | ~08:59 | **no** |
| `genaiops.call` (deliberately unscored control) | ~09:00 | **no** |

`force_flush()` returned true every time — no warning was printed by any run.
The losses are **not** in time order: 08:57 arrived while 08:50 and 08:59 did
not, which is what rules out simple lag as a complete explanation.

**Consequence**: `query_evaluations.py --trace-id` currently reports "no
evaluation found" for a call that *was* scored. That output is correct about
what the trace store contains and wrong about what happened — and it is
indistinguishable from FR-008's genuine absence case, which is exactly the
confusion this feature exists to prevent. Until F6 is resolved, T013, T014,
T020 and T025 cannot be honestly verified.

**Leading hypothesis, untested**: `azure-ai-evaluation` runs its evaluators
through a bundled legacy promptflow tracing layer, which configures its own
OpenTelemetry provider. If it replaces the global provider after
`configure_azure_monitor()` installed one, then `trace.get_tracer_provider()
.force_flush()` flushes a provider that never held the span — returning true
having exported nothing. That would explain a true return with no delivery, and
it is the same class of bug as block 3's original lost span, one layer up. It
does not explain the lost `genaiops.call`, which runs block 3's unmodified
script, so there may be two causes.

**The cheapest next step is free and already running**: re-query the workspace
after several hours. If the missing spans have appeared, this is ingestion lag
of an unexpected magnitude and the finding shrinks to "the 1–3 minute figure in
`query_trace.py` is wrong." If they are still absent, they were never exported,
and the flush path needs instrumenting — starting by printing the tracer
provider's identity before and after the evaluator call.

---

## F7 — A relative fixture path made `prompt_version()` confidently wrong (mine, fixed)

`prompt_version()` runs git with `cwd` set to the file's parent, so a relative
path like `fixtures/unsupported_claim.json` reached git as a pathspec resolved
from inside `fixtures/`. Git matched nothing, and the function returned
`"uncommitted"` for a file committed in `b3a350b`.

Not an error and not empty — a plausible wrong answer, recorded onto a span as
fact. `call_model.py` avoided it by resolving the path first; this script did
not. Fixed by resolving inside `prompt_version()` itself, so no caller can
reintroduce it.
