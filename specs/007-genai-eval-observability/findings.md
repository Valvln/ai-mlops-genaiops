# Findings: what the first real run of Block 4 turned up

Recorded 2026-08-23, during the implementation session that redeployed
`infra/foundry.bicep` and ran the first evaluations against it. Everything here
was **measured, not reasoned about** — each entry carries the command and the
output that produced it.

Five of these are defects in things this feature's plan assumed were already
sound. That is the point of writing them down separately from `research.md`:
research recorded what was decided **before** building, and these are what
building disproved.

**Status, updated 2026-08-23 evening**: F1, F2, F3, F7 and F8 are **fixed and
verified**. F4 is worked around. F5 is resolved in code. **F6 is still open**,
and is now the only thing between this feature and a complete verification —
the fresh workspace F8's fix produced did *not* cure it, which disproved the
hypothesis this document carried for most of the day.

The template fixes were made after the author authorised them ("we'll fix it
before finishing the block"), and each was proven by deployment rather than by
`az bicep build`, which could see none of them:

| Run | Template | Result |
| --- | --- | --- |
| `block4-001` | unchanged | Failed — F1, project lost the race |
| `block4-002` | unchanged, re-run | Failed — F2, connection not re-deployable |
| `block4-fixed-001` | `dependsOn` project→connection | Failed — project raced the *deployment* instead |
| `block4-fixed-002` | full chain | Failed — F2 proper: both connections shared a name |
| `block4-fixed-003` | distinct connection names | **Succeeded** |
| `block4-fixed-004` | same template, second run | **Succeeded — idempotent** |

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

**Fixed, and the first attempt was wrong in an instructive way.** Adding a
single `dependsOn` between the project and the account-level connection moved
the race rather than removing it: the next run failed with the project losing
to the **model deployment**. The pairs were never the point. *Every* child of a
Cognitive Services account contends for the same account-level lock, so the
template now chains all four in sequence — account → deployment → project →
account connection → project connection. Verified by `block4-fixed-003`.

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

**Fixed, and the cause was simpler than the error suggested.** The two
connections were declared with the *same name*. A project is projected as an
AML workspace sharing the account's connection namespace, so whichever was
created second collided with the first and was refused as an unauthorised
update. Feature 006 never saw it because F1's race happened to create the
project-level one first; the moment F1's chain fixed the ordering, the
collision became deterministic. The project-level connection now carries a
`-project` suffix. Verified by `block4-fixed-004`, a second consecutive
deployment that succeeded — the idempotency this template did not previously
have.

Worth noting for later: neither connection is read by anything in this
repository. `call_model.py` takes the App Insights connection string from the
component directly, because reading a connection needs a data action neither
Owner nor `Cognitive Services OpenAI User` carries. They are portal wiring, and
they cost two deployment failures to keep.

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

### Diagnosed, same day, 19:45–20:00 — and the client is innocent

The re-query settled the lag question first: **11 hours later, still three
spans.** Not lag. Then four tests, in order, each eliminating a suspect.

**1. The leading hypothesis was wrong.** `azure-ai-evaluation` does *not*
replace the tracer provider. Printing the provider's identity at four points —
before `configure_azure_monitor`, after it, after importing the evaluators,
after constructing one — gives the same object and the same four span
processors throughout (`id=4520623056`, `processors=4`). The bundled promptflow
tracing never touches the global provider. Recorded because a plausible,
well-reasoned hypothesis that turns out to be false is worth as much as a
confirmed one, and cheaper to re-derive wrongly later than to look up here.

**2. It is not sampling or a cap.** The component reports
`samplingPercentage: null`, `DailyCap: null`; the workspace reports
`dailyQuotaGb: -1`.

**3. It is not the code under test.** Five probe processes — no evaluator, no
model call, just `configure_azure_monitor` → one span → `force_flush` — behave
identically: `force_flush=True`, nothing arrives. Structurally the same as
`call_model.py`, which worked at 08:33 and stopped working by 09:00.

**4. Application Insights is accepting the data.** Running a probe with the
exporter's own logging on:

```text
POST //v2.1/track HTTP/1.1" 200
Transmission succeeded: Item received: 8. Items accepted: 8
```

An HTTP 200 and an explicit per-item acknowledgement. **`force_flush` was
honest, the exporter did its job, and the ingestion endpoint accepted every
item.** The spans were exported and acknowledged, and then did not appear.

**Where the gap actually is**: between Application Insights accepting an item
and the Log Analytics workspace surfacing it as a queryable row. That is
server-side, and nothing in this repository can fix it. The evidence that it is
table-specific rather than total:

| Table | Latest row (queried 19:54) |
| --- | --- |
| `AppMetrics` | **19:48:56** — from the probe processes minutes earlier |
| `AppPerformanceCounters` | **19:48:55** — likewise |
| `AppDependencies` | **09:00:56** — nothing for 11 hours |

Telemetry from the same processes, over the same connection string, in the same
minute: metrics land, dependencies do not. Custom spans are dependencies.

### The F6 hypothesis was tested and is wrong

The obvious suspect was F8: the workspace had been restored from soft-delete
rather than created, so an incomplete restore would explain a half-working
ingestion pipeline. It was testable, and it was tested — teardown with
`--force`, redeploy, verify `createdDate` is today and the `customerId` is new,
then re-run everything against a workspace that had never existed before.

**The loss reproduced exactly.** Of roughly eleven `genaiops.*` spans emitted
into the fresh workspace, three arrived:

| Emitted | Arrived |
| --- | --- |
| `genaiops.call` × 6 | 2 |
| `genaiops.eval` × 5 | 1 |

Recorded here because a disproved hypothesis is worth as much as a confirmed
one, and this one was expensive: it drove a full teardown and redeploy. That
work was not wasted — F8 is real, and F1/F2/F3 were fixed and proven along the
way — but it did not touch F6.

### What is actually known

- **The client is not at fault.** `force_flush()` returns true; the exporter
  logs `HTTP 200` and `Transmission succeeded: Item received: 8. Items
  accepted: 8`. Application Insights accepts every item.
- **It is not the evaluation SDK.** The tracer provider is never replaced
  (same object, same four processors, checked at four points), and block 3's
  unmodified `call_model.py` loses spans at the same rate as `evaluate_call.py`.
- **It is not sampling as configured.** `samplingPercentage: null`,
  `DailyCap: null`, `dailyQuotaGb: -1`.
- **It is not the workspace's history.** Reproduced on a workspace minutes old.
- **It is not another table.** `AppRequests` is empty; the spans are nowhere.
- **Child spans survive when their parent does not.** In a lost run, the
  auto-instrumented token requests arrive under the very `OperationId` whose
  root span is missing. Whatever drops these is selecting *within* a batch that
  was acknowledged as fully accepted.
- **The early spans of a session survive; later ones do not.** The first two
  calls into a brand-new component landed; almost nothing after did. That shape
  — fine at first, then lossy — is what an adaptive, service-driven sampler
  looks like from the client side, and the SDK is observably fetching
  `AzMonSDKDynamicConfiguration` from the live-metrics endpoint. **Untested**,
  and named here as the next thing to try, not as a conclusion.

### What it costs this feature

- **SC-002 is verified**, but only because a retained eval span was caught:
  `query_evaluations.py --trace-id` returned the joined record — prompt version
  `4b0d037`, deployment, relevance 5.0 against threshold 3, `pass`, the judge's
  reasoning, and the response — from a separate invocation. The mechanism is
  proven; the store it depends on is not reliable.
- **FR-008 is verified**: an unscored call is reported as an absence in words.
- **T020 and T025 are not verified.** Both need specific records to survive
  ingestion, and repeated attempts did not land one. The evaluations themselves
  ran correctly every time — groundedness 5.0 `pass` on a grounded answer, 4.0
  `fail` on the fixture, reproducibly — so what is unproven is retrieval of
  those particular records, not the scoring behind them.
- **SC-006's counter under-reports, and this is the sharpest lesson here.**
  `--count-invocations` returned **3** for a session that made roughly **13**
  model calls. The count is deliberately derived from the trace store rather
  than a side tally, on the principle that a second source of truth drifts —
  and that principle is still right. But it means the cost guardrail inherits
  the trace store's losses, and it fails *toward under-reporting*: the
  flattering direction. A budget check that silently reads low is worse than
  none, and that is worth carrying into any future cost control built this way.

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

---

## F8 — The "disposable" environment is not disposable: the workspace came back with its old data

**Severity**: undermines a premise the whole feature is built on, and is the
prime suspect behind F6.

`az resource list` after the redeploy showed the expected four resources, and
T008 passed. But the Log Analytics workspace reports:

```json
{ "created": "2026-08-19T08:29:31Z", "modified": "2026-08-23T08:28:44Z" }
```

**Created on 2026-08-19** — feature 006's deployment date. Today's deploy did
not create a workspace; it *restored* feature 006's, which `az group delete`
had only soft-deleted. Querying with no time filter proves the data came back
with it:

```text
genaiops.call | n = 5 | 2026-08-19 08:37:14 -> 2026-08-23 08:34:54
```

Five call spans, the earliest from four days ago and three days after the
resource group was supposedly destroyed.

**Why this matters beyond tidiness**:

- **It is a second soft-delete trap, and worse-behaved than R1's.** The
  Cognitive Services hold *failed loudly* and forced the explicit purge that
  became T001. A Log Analytics workspace inside its recovery window is restored
  **silently, and reported as a successful create.** A trap that fails is a
  trap you handle once; a trap that succeeds wrongly is one you never notice.
- **It weakens SC-001's redeployment-as-proof claim.** "The template recreated
  what it describes" is exactly what a restore imitates. `az resource list`
  cannot tell the two apart — only `createdDate` can, and neither T008 nor
  `contracts/foundry-redeployment.md` step 8 thought to look.
- **It contaminates any measurement scoped by resource, not by time.** SC-006's
  invocation cap counts spans in the trace store; feature 006's three calls are
  now in that store. The `--since` window happens to exclude them, which is
  luck, not design.
- **It is the leading explanation for F6.**

**Fix, when authorized**: teardown must delete the workspace explicitly with
`az monitor log-analytics workspace delete --force true` before or after
`az group delete`, exactly as T001 purges the Foundry account — and T008 should
assert `createdDate` is today, so a restore can never again be mistaken for a
create.