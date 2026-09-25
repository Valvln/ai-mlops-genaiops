# Tracing a generative AI call — OpenTelemetry, App Insights, and silent losses

**Status: built, and both things that shipped broken were defaults, not code.**
Feature 006 emitted spans from `call_model.py`, read them back from a separate
process with `query_trace.py`, and discovered by measurement that a span queued
in a batch processor is not a span that was exported (§ 7). Feature 007 then
lost spans for two days to the SDK's **default sampler** (§ 7b, added
2026-09-22), which the first version of this note had no section for. Everything
else below comes from the Microsoft Learn pages under *Sources*, read on
**2026-08-21**.

This is Domain 4 material that Domain 3 keeps needing. The evaluation half of
Domain 4 — groundedness, relevance, safety evaluators — is **not** in this note
and has not been built.

---

## 1. Where traces go

> «Foundry stores traces in **Azure Application Insights** using OpenTelemetry.
> **New resources don't provision Application Insights automatically.**
> Associate (or create) a resource **once per Foundry resource**.»

Three consequences, in the order they bite:

1. A brand-new Foundry resource has **no** telemetry target. An instrumented app
   will run, succeed, and show nothing in the portal's **Tracing** blade. That is
   the expected state, not a fault.
2. The association is on the **Foundry resource**, not the project: «Once the
   connection is configured, you're ready to use tracing in **any project within
   the resource**.»
3. Application Insights sits on a **Log Analytics workspace**, which is where the
   data actually lands — and therefore where the read permissions live (§ 4).

### Permissions to *create* the association

- to connect an **existing** App Insights: at least **Contributor** on the
  Foundry resource (or hub)
- to create a **new** one: **Contributor on the resource group** as well

---

## 2. Instrumenting the call

```bash
pip install azure-ai-projects azure-monitor-opentelemetry \
            opentelemetry-instrumentation-openai-v2
```

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

project_client = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint="https://<resource>.services.ai.azure.com/api/projects/<project>",
)
connection_string = project_client.telemetry.get_application_insights_connection_string()

configure_azure_monitor(connection_string=connection_string)
OpenAIInstrumentor().instrument()
```

Two ways to reach the telemetry target, and they have different prerequisites:

| Route | Needs |
| --- | --- |
| **Project endpoint** → `telemetry.get_application_insights_connection_string()` | Microsoft Entra ID configured in the application, **and** the ability to read the project's connection |
| **App Insights connection string** directly | nothing but the string (portal: *Project → Tracing → Manage data source → Connection string*) |

> «Using a project's endpoint requires configuring Microsoft Entra ID in your
> application. **If you don't have Entra ID configured, use the Azure Application
> Insights connection string** as indicated.»

⚠️ **This is the fork feature 006 took deliberately.** Reading the project's
connection is a **data action** requiring
`Microsoft.CognitiveServices/accounts/AIServices/connections/read`, and the only
built-in role carrying it grants the whole Cognitive Services data plane for one
lookup. The connection string was taken from the App Insights resource instead —
the second row of that table — and the refusal was left in place. The reasoning
is in `genaiops/foundry-block3/README.md`; the permission surface is in
`foundry-rbac-and-authentication.md` § 1.

---

## 3. What a span carries, and what it doesn't

The GenAI semantic-convention attributes, from Learn's own console output:

```json
"name": "chat deepseek-v3-0324",
"kind": "SpanKind.CLIENT",
"attributes": {
    "gen_ai.operation.name": "chat",
    "gen_ai.system": "openai",
    "gen_ai.request.model": "deepseek-v3-0324",
    "server.address": "my-project.services.ai.azure.com",
    "gen_ai.response.model": "DeepSeek-V3-0324",
    "gen_ai.response.finish_reasons": ["stop"],
    "gen_ai.response.id": "…",
    "gen_ai.usage.input_tokens": 14,
    "gen_ai.usage.output_tokens": 91
}
```

`gen_ai.usage.input_tokens` and `output_tokens` are the hook for **cost
observability** — Domain 4's «track and optimize cost metrics, including token
consumption» is this attribute, aggregated.

Note what is **absent**: the prompt text and the response text.

### Message content is opt-in

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

Learn lists it as *«(Optional) Capture message content»*. Without it you get
durations, token counts, model names and finish reasons — everything except what
was said. **The default is privacy-preserving, and it is the default.**

The exam-shaped inversion: "we can see latency and token counts but not the
prompts" is not a bug, a permission problem, or an SDK choice. It is one
environment variable.

### Custom spans and attributes

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("assess_claims_with_context")
def assess_claims_with_context(claims, contexts):
    current_span = trace.get_current_span()
    current_span.set_attribute("operation.claims_count", len(claims))
    ...
```

The decorator groups every model call inside the method into **one span**, which
is how business logic becomes legible next to the model calls. Custom attributes
are how a call is tied back to something the platform doesn't know about — which
is exactly what `call_model.py` does with the prompt file's git revision.

### What the portal shows

Per trace: **Trace ID**, start time, duration, status, and **Operations** (the
number of spans). Drilling in gives the execution timeline, input and output per
operation, timing, errors, and custom attributes.

---

## 4. Reading traces back

> «Make sure you have the **Log Analytics Reader** role assigned in your
> Application Insights resource. If the underlying Log Analytics tables are
> **protected**, also assign the **Privileged Monitoring Data Reader** role.»

Two roles, one condition. Both are **Azure Monitor** roles on the App Insights
resource — not Foundry roles on the Foundry resource. Writing a trace and reading
it back are governed by two different services.

⚠️ Feature 006's plan predicted that `Log Analytics Reader` would be needed and
that inference would need nothing. **Both were backwards**: the Log Analytics
query worked under Owner because it is a control-plane action, and inference
failed because it is a data action. The Learn guidance above is the *documented*
requirement for the general case; the observed behaviour on an Owner principal was
that it was already satisfied. Those are not in conflict — an Owner has the
control-plane actions a Log Analytics query needs — but assuming the plan was
right would have hidden the real lesson.

The reading itself is a **separate process** concern, and that is the point of
the exercise: a trace you can only see in the terminal that produced it is not
observability. `query_trace.py` is this repository's proof.

---

## 5. Tracing without Azure

Two documented paths, both free.

### Console exporter, for CI

> «It might be useful to also trace your application and send the traces to the
> local execution console. This approach might be beneficial when running **unit
> tests or integration tests** in your application **using an automated CI/CD
> pipeline**. Traces can be sent to the console and captured by your CI/CD tool
> for further analysis.»

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)
```

`OpenAIInstrumentor().instrument()` is unchanged; **only the exporter differs**.
That is the design point of OpenTelemetry and the reason the answer to "how do we
trace in CI without App Insights" is not "you can't".

Note the processor: **`SimpleSpanProcessor`**, which exports each span as it
ends. See § 7 for why that choice is not incidental.

### Foundry Toolkit, for local development

A local OTLP-compatible collector in VS Code — «perfect for development and
debugging without needing cloud access», supporting the OpenAI SDK and other
frameworks through OpenTelemetry.

---

## 6. The networking dependency

If Foundry is deployed with virtual network injection and egress passes a
firewall, tracing needs two FQDNs allowlisted, listed under *Evaluations &
Traces*:

- `*.blob.core.windows.net`
- `settings.sdk.monitor.azure.com`

«Used for the evaluators catalogue and for **sending results to the linked
Application Insights resource**.» Without them, an isolated deployment produces
telemetry that never leaves. See `network-isolation.md` for the rest of the
outbound story.

---

## 7. ⚠️ The failure that is not documented anywhere above

**Measured here, on 2026-08-19. Not a Learn claim.**

The first version of `call_model.py` ended when its span closed and let the
OpenTelemetry **batch** processor ship whatever it had at interpreter exit. One
call had already been retrieved successfully, so tracing looked proven. A second
call then went missing: three hours later the workspace still held exactly one
record, so it was a loss and not ingestion lag.

**A span queued in a batch processor is not a span that was exported**, and a
short-lived CLI process is exactly where that gap opens — the process is gone
long before the next scheduled export. The fix is an explicit flush before exit.

Two things worth carrying beyond the bug:

- **What exposed it was a success criterion demanding two records instead of
  one.** A single retrieval would have shipped a mechanism that works about half
  the time. This is the repository's recurring failure mode — a check that passes
  while its objective is missed — caught for once by the design of the check.
- Learn's console-tracing snippet uses **`SimpleSpanProcessor`**, not the batch
  one. For a short-lived process that is the safer default, and the sample is
  quietly making the same point.

**Observed ingestion lag, for calibration: 2–3 minutes.** Anything still missing
after that is missing, not late.

---

## 7b. Sampling — the default that drops your spans

**Read 2026-09-22, after it cost this repository two days as F6.** This is the
section that was missing when § 7 was written, and the two failures are cousins:
both are long-lived-service machinery applied to a short-lived CLI.

### Two samplers, and only one of them is on the Azure resource

| | Where it runs | Default | How it reads when you check it |
| --- | --- | --- | --- |
| **SDK sampling** | in your process, at span creation | **on** | invisible from `az`; you must read the SDK |
| **Ingestion sampling** | Azure, at the ingestion endpoint | off | `samplingPercentage: null` on the component |

Checking the component and finding `samplingPercentage: null` proves only that
the **second** one is off. This is the exam-shaped trap: the two have the same
name and different addresses.

> «The Application Insights OpenTelemetry distros include a **default sampler**.
> The specific sampler and its rate depend on the language and distro version.»

Ingestion sampling is documented as a fallback, «not recommended»: «It drops
data at the Azure Monitor ingestion point and offers no control over which
traces and spans are retained.» Use it only when you cannot change the source.

### What is sampled and what is not

> - «Sampling decisions apply to **traces** (spans).»
> - «**Logs** that belong to unsampled traces are dropped by default.»
> - «**Metrics** are never sampled.»

That last line is diagnostic gold and is why F6 looked like a broken ingestion
pipeline: `AppMetrics` kept landing while `AppDependencies` went silent, from
the same process, over the same connection string, in the same minute. Metrics
arriving proves the pipe is open. It says nothing about your spans.

### Verifying whether you are being sampled

Learn's own query, which reads the retained percentage out of `itemCount`:

```kusto
union requests,dependencies,pageViews,browserTimings,exceptions,traces
| where timestamp > ago(1d)
| summarize RetainedPercentage = 100/avg(itemCount) by bin(timestamp, 1h), itemType
```

> «If you see that `RetainedPercentage` for any type is less than 100, then that
> type of telemetry is being sampled.»

**This is the check F6 never ran**, and it would have answered in one query what
took two days of elimination. Note it works per `itemType`, so it also shows the
metrics/dependencies split directly.

### Configuring it

Two routes, and **environment variables take precedence over code**:

```bash
export OTEL_TRACES_SAMPLER="microsoft.fixed_percentage"   # or microsoft.rate_limited
export OTEL_TRACES_SAMPLER_ARG=0.1                        # ~10%; or traces/sec
```

```python
configure_azure_monitor(connection_string=..., sampling_ratio=1.0)  # keep everything
```

`always_on` is also accepted as a sampler type. For a study harness or any
short-lived CLI, **keep 100%**: the volume is a handful of spans, and the whole
point of the exercise is that every record is retrievable.

### ⚠️ The Python default: documented on Learn, and its startup behaviour measured here

**`azure-monitor-opentelemetry` 1.8.6 (2026-02-05) changed the Python default.**
Learn states it on the Python tab of *Configuring OpenTelemetry in Application
Insights* (§ Enable sampling):

> «Starting from version 1.8.6, **rate-limited sampling is the default**.»
> «If you don't set any environment variables or provide either `sampling_ratio`
> or `traces_per_second`, `configure_azure_monitor()` uses **RateLimitedSampler**
> by default.»

The package changelog adds the rate, which the Learn page does not give:

> «The default sampling behavior has been changed from ApplicationInsightsSampler
> with 100% sampling (all traces sampled) to **RateLimitedSampler with 5.0
> traces per second**.»

Neither source describes the behaviour at process start. That part is measured
here.

"5 traces per second" sounds impossible to hit with one span. It is not, because
the limiter is adaptive: it derives its percentage from an exponentially decayed
window that **starts at zero**, with a 0.1 s adaptation constant. Measured
against 1.8.9:

| Process age at first span | Sampling percentage |
| --- | --- |
| 0 ms | **0%** |
| 100 ms | 50% |
| ≥ 500 ms | 100% |

**A rate limiter that is harshest at startup is the opposite of what the name
suggests**, and a CLI that configures, calls and exits lives entirely inside its
worst case. Twelve spans emitted back to back: 1 recorded by default, 12 with
`sampling_ratio=1.0`.

The drop happens at span creation, so the span is never queued and never
exported. **`force_flush()` still returns `True`** — truthfully, because there
is nothing to flush — and the ingestion endpoint still answers `Items accepted`
for the telemetry that *was* sent. Three green signals, none of which means your
span exists. See `specs/007-genai-eval-observability/findings.md` § F6.

Two rules worth carrying:

- **A pinned range is not a pinned behaviour.** `>=1.6,<2.0` accepted a
  documented breaking change in a default, with no commit in this repository.
- **Check the SDK's sampler, not just the resource's.** They share a name and
  answer different questions.

---

## 8. What this note would cost to verify

**Everything in §§ 2–5 is already spent or free.** The spans, the retrieval and
the flush bug cost ~1,300 tokens in total, against a `GlobalStandard` deployment
that bills nothing at rest. Application Insights bills per GB ingested; a handful
of spans is not a measurable quantity.

The one standing cost to be aware of is the **Log Analytics workspace**, which
outlives the terminal that made the call and is the reason the retrieval works at
all. It died with `rg-ai300-foundry`.

Untested here, and cheap if it is ever wanted: **the console exporter path**
(§ 5), which needs no Azure resource whatsoever and would make the CI story real
rather than read.

---

## Sources

- [View trace results for AI applications using OpenAI SDK](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/trace-application) — read 2026-08-21 via `/azure/ai-foundry/concepts/trace`, which resolves here; §§ 1–5
- [How to configure network isolation for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link) — read 2026-08-21; the firewall allowlist in § 6
- [Tracing in Foundry Toolkit](https://code.visualstudio.com/docs/intelligentapps/tracing) — referenced by the Learn page for § 5
- `foundry-rbac-and-authentication.md` § 1 — why reading a connection is a data action
- `network-isolation.md` — the outbound story § 6 depends on
- `genaiops/foundry-block3/call_model.py`, `query_trace.py`, `README.md` — § 7, measured here
- [Sampling in Azure Application Insights with OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling) — read 2026-09-22; § 7b, including "Metrics aren't sampled" and the `RetainedPercentage` query
- [Configuring OpenTelemetry in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration#enable-sampling) — read 2026-09-22; reread 2026-09-25 (ms.date 2026-06-19); the Python sampler environment variables and the Python default in § 7b
- [azure-monitor-opentelemetry CHANGELOG, 1.8.6](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/monitor/azure-monitor-opentelemetry/CHANGELOG.md) — read 2026-09-22; the default sampler's rate of 5.0 traces per second, which the Learn page does not give
- `specs/007-genai-eval-observability/findings.md` § F6 — § 7b's measurements, and the two days the missing section cost
