# Findings: what the first real run of Block 4 turned up

Recorded 2026-08-23, during the implementation session that redeployed
`infra/foundry.bicep` and ran the first evaluations against it. Everything here
was **measured, not reasoned about** — each entry carries the command and the
output that produced it.

Five of these are defects in things this feature's plan assumed were already
sound. That is the point of writing them down separately from `research.md`:
research recorded what was decided **before** building, and these are what
building disproved.

**Status, updated 2026-09-22**: F1, F2, F3, F5, F7 and F8 are **fixed and
verified**. F4 is worked around and is a defect in the SDK, not here. **F6 is
fixed** — reopened on 2026-09-22 and traced to `RateLimitedSampler`, the default
sampler `azure-monitor-opentelemetry` adopted in 1.8.6. It was never service-side.
The fix is one argument in two files; the diagnosis is at the end of F6.

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

## Conformance audit against the official documentation — 2026-09-22

These eight findings were measured in August with no source read beside them,
which is the gap constitution § 1.1.0 was written to close. Each was read
against Microsoft Learn and the SDK references on 2026-09-22. No Azure resource
was created; everything below is a documentation read or a local measurement.

| | Finding | What the source says | Verdict |
| --- | --- | --- | --- |
| **F1** | account-level deployment race | ARM deploys resources in parallel unless ordered; serialize children of one account with `dependsOn`. The conflict is documented behaviour of a busy parent, not a defect. | **Conformant.** Fix matches prescribed practice. |
| **F2** | connection not re-deployable | Same-name collision across the account's connection namespace. Not documented for Foundry projects-as-AML-workspaces; the error text names the projection but no page explains it. | **Divergent, source silent.** Fix is right; the silence is a gap worth keeping. |
| **F3** | `capacity: 1` = 1 request/min | Documented: capacity sets TPM/RPM on a token-billed SKU and is a throttle, not a reservation. | **Conformant.** Template now says 10. |
| **F4** | `credential` in model config unusable | Learn documents `credential: NotRequired[Any]` as a supported field, "Compatible with azure.core.credentials.TokenCredential". It cannot work: the SDK validates TypedDicts with `isinstance()`, which rejects `Any`. Still reproduces on 1.18.3. | **Defect in the SDK.** Documented field, unusable implementation, misleading error. Workaround stands. |
| **F5** | default groundedness threshold passes a fabrication | Learn confirms the mechanics exactly: scale 1–5, default threshold 3, "scores at or above the threshold are considered passing". It makes no claim that 3 is right for a gate. | **Conformant, and the finding is about judgement, not conformance.** The default is documented; choosing 5 is ours to justify. |
| **F6** | eval spans never queryable | **Contradicted by the source.** The distro installs a default sampler; ingestion sampling and SDK sampling are different things with the same name; metrics are never sampled while spans are. | **Was divergent-and-misdiagnosed. Now fixed.** See below. |
| **F7** | relative path made `prompt_version()` wrong | Git pathspec resolution, not an Azure surface. No documentation involved. | **Ours, fixed.** Out of audit scope. |
| **F8** | teardown restored the old workspace | **Documented precisely**, and the mechanism explains the silence: recovery «is performed by **re-creating** the Log Analytics workspace with the details of the deleted workspace — Subscription ID, Resource group name, Workspace name, Region». Soft-delete runs 14 days; `--force` deletes permanently. | **Conformant behaviour, divergent runbook.** Not a defect. `infra/DEPLOY.md` documents the Key Vault trap and not this one. |

**Three things this audit changed**, in descending order of consequence:

1. **F6 was wrong and is now fixed** — the one finding where reading the source
   reversed the conclusion rather than confirming it.
2. **F8 is reclassified.** It was filed as a trap and as "the prime suspect
   behind F6". It is neither: it is the documented recovery path, working as
   specified, and it had nothing to do with F6. What remains real is the runbook
   gap — a same-name redeploy silently recovers, and `az resource list` cannot
   tell recovery from creation.
3. **F4 is confirmed as a source defect**, which is the rarest of the three
   outcomes and worth citing as such: the documentation describes a field the
   implementation cannot accept.

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

**Severity**: **fixed on 2026-09-22.** The cause is the SDK's default sampler,
not Application Insights. Closed as a service-side limitation on 2026-08-25 and
reopened when the official documentation was finally read against it — the
sections below are kept in the order they were written, because the wrong
conclusion and its evidence are the useful part.

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

> **Wrong, and this is the step that cost two days.** Those three values
> describe **ingestion** sampling, configured on the Azure resource. They say
> nothing about **SDK** sampling, which runs first, in the process, and is on by
> default. The test was sound and answered a different question than the one
> asked. See the 2026-09-22 section.

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

> **Wrong conclusion, correct evidence.** The gap is upstream of the export, not
> downstream of it: the lost spans were never sent, so the acknowledged items
> are a different population from the missing ones. The table split below is
> real and turns out to be the strongest clue in this document — Learn states
> that metrics are never sampled while spans are, which is exactly the
> asymmetry measured here. It was read as evidence of a broken ingestion
> pipeline rather than of a working sampler.

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
  `DailyCap: null`, `dailyQuotaGb: -1`. — **This line is the error.** It is
  sampling, as *defaulted*: those fields cover ingestion sampling only, and the
  SDK's own sampler was never inspected.
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
  and named here as the next thing to try, not as a conclusion. — **Right about
  the sampler, wrong about where it runs.** It is adaptive and it is in the SDK,
  not in the service; the live-metrics fetch was a coincidence. Tested on
  2026-09-22, and this was the answer.

### Reopened and fixed — 2026-09-22, by reading the source instead of the service

**The last hypothesis was right about the mechanism and wrong about the
address.** There is an adaptive sampler, and it is not service-side. It is in
this repository's own dependency tree, and it was never searched for because
`samplingPercentage: null` on the component had been read as "sampling is off".
That reading is correct about *ingestion* sampling and says nothing about the
SDK, which samples first and independently.

`configure_azure_monitor()` installs a sampler whether or not one is asked for.
In `azure-monitor-opentelemetry` **1.8.6 (2026-02-05)** the default changed, as
a documented breaking change:

> «The default sampling behavior has been changed from ApplicationInsightsSampler
> with 100% sampling (all traces sampled) to **RateLimitedSampler with 5.0 traces
> per second**.»

Both blocks pin `azure-monitor-opentelemetry>=1.6,<2.0` and both resolve to
**1.8.9**, so this repository adopted the change without a commit.

**Why a 5-per-second limit drops almost everything in a script that emits one
span.** `RateLimitedSampler` does not count spans against a fixed window. It
derives a percentage from an exponentially decayed window
(`_rate_limited_sampling.py`), and that window **starts at zero**:

```python
initial_nano_time = int(time.time_ns())
self._state = _State(0.0, 0.0, initial_nano_time)   # effective_window_nanoseconds = 0
```

With `effective_window_nanoseconds = 0` the computed probability is 0, so the
percentage climbs from 0% only as wall-clock time passes, at the hardcoded
0.1 s adaptation constant. Measured against the installed package:

| Age of the process when the first span is emitted | Sampling percentage |
| --- | --- |
| 0 ms | **0.00%** |
| 10 ms | 5.00% |
| 100 ms | 50.00% |
| ≥ 500 ms | 100.00% |

A rate limiter that is *most aggressive at process start* is the exact inverse
of what the name suggests, and a short-lived CLI is the shape it penalises
hardest. This is the same class of trap as `genai-tracing.md` § 7 — a
short-lived process losing spans to machinery designed for long-lived services.

**Every symptom this document recorded is accounted for, including the ones
that argued against the client:**

| Recorded symptom | What the sampler does |
| --- | --- |
| `force_flush()` returns true | A dropped span is **never queued**. Nothing to flush is not a failure to flush. |
| `HTTP 200`, `Items accepted: 8` | Those eight items are metrics and performance counters, which are never sampled. |
| `AppMetrics` lands, `AppDependencies` does not | Learn: «**Metrics** are never sampled.» Sampling decisions apply to spans. |
| Losses not in time order | The decision is `DJB2(trace_id) < percentage` — a function of the trace id, not of arrival order. |
| Child spans survive a missing parent | `parent_context_sampling()` honours a **recording** parent's rate; a child sampled under a different root is decided separately. |
| Early spans of a session survive, later ones do not | Each process re-enters the 0% window; whichever span happens to land after ~0.5 s survives. |
| Reproduced on a workspace minutes old | The sampler is client-side. Workspace age is irrelevant. |
| Block 3's unmodified `call_model.py` loses at the same rate | Same distro, same range, same 1.8.9, same default. This was read as evidence of a shared *service* cause. It was evidence of a shared *dependency*. |

**Verified offline, at no cost and with no Azure resource.** `configure_azure_monitor()`
contacts nothing at configure time, so a syntactically valid fake connection
string exercises the real wiring. Twelve spans emitted back to back:

| Configuration | Sampler installed | Spans recorded |
| --- | --- | --- |
| as block 4 shipped | `RateLimitedSampler{5.0}` | **1 / 12** |
| `OTEL_TRACES_SAMPLER=always_on` | `AlwaysOnSampler` | 12 / 12 |
| `sampling_ratio=1.0` | `ApplicationInsightsSampler{1.0}` | **12 / 12** |

1 in 12 is the loss rate this document measured against Azure (3 of ~11).

**Fixed in code, not in the environment.** `sampling_ratio=1.0` is passed to
`configure_azure_monitor()` in both `qa-observability/foundry-block4/evaluate_call.py`
and `genaiops/foundry-block3/call_model.py`. The environment-variable route
(`OTEL_TRACES_SAMPLER=always_on`) works identically and was rejected: it lives
in a shell rather than in the source, so it cannot be reviewed, and
`azure-monitor-opentelemetry` 1.8.3 shipped a fix for «default value overriding
user-configured sampling ratio», which is a warning about relying on precedence
between the two routes.

**Not re-verified against Azure.** The environment is torn down and this session
created nothing. What is proven is that the sampler drops the spans and that the
argument stops it, both measured against the installed package. What is not
proven is a round trip into Log Analytics. T013, T014, T020 and T025 stay
unverified until an environment exists to run them against — but the reason they
failed is no longer unknown, and is no longer service-side.

**What this cost, and why.** Two days of diagnosis eliminated the client, the
evaluation SDK, the workspace history and every other table, and concluded
"service-side" because every layer *the repository owns* had been cleared. The
sampler was in none of those layers by that definition, and in all of them by
any useful one: a transitive default of a pinned dependency. The constitution's
1.1.0 rule — read the source alongside the measurement — was written after a
measurement that was sound and whose conclusion was incomplete. This is the same
failure, found by applying that rule to a finding that predated it.

### What the loss taught before it was fixed, and still teaches

- **A trace store is a dependency, not a given.** Everything downstream of it —
  retrieval, comparison, the invocation counter — inherits its losses.
- **`force_flush()` returning true, `HTTP 200`, and `Items accepted: 8` are
  three separate acknowledgements, and none of them is "queryable".** A record
  is verified when a *separate process reads it back*, which is exactly why
  `evaluate_call.py` and `query_evaluations.py` are separate programs.
- **The under-reporting direction matters more than the magnitude.** See the
  invocation counter below.

Recorded as a limitation in `qa-observability/foundry-block4/README.md`
("What is not proven") and in tasks.md T031, which previously pointed at the
promptflow hypothesis this document has since disproved.

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