# Tracing a generative AI call: OpenTelemetry, Application Insights, lost spans

**Status: built.** Feature 006 emits spans from `call_model.py` and reads them
back from a separate process with `query_trace.py`. Two defects reached this
code, and both came from SDK defaults: a batch processor that did not export
before exit (§ 7), and the SDK's default sampler, which cost feature 007 two
days (§ 7b). Both are measured here. Everything else comes from the Microsoft
Learn pages under *Sources*, read on **2026-08-21**; the sampling pages were
read on 2026-09-22.

Evaluation is in `genai-evaluation-workflows.md`, `genai-quality-evaluators.md`
and `genai-risk-and-safety-evaluation.md`. Dashboards, platform metrics and cost
are in `genai-production-monitoring.md`.

---

## 1. Where traces go

> «Foundry stores traces in **Azure Application Insights** using OpenTelemetry.
> **New resources don't provision Application Insights automatically.**
> Associate (or create) a resource **once per Foundry resource**.»

- A new Foundry resource has no telemetry target. An instrumented app runs,
  succeeds, and shows nothing on the portal's **Tracing** page. This is the
  expected state.
- The association belongs to the **Foundry resource**: «Once the connection is
  configured, you're ready to use tracing in **any project within the
  resource**.»
- Application Insights stores its data in a **Log Analytics workspace**. The
  read permissions are set there (§ 4).

Permissions to create the association:

- connect an **existing** Application Insights: at least **Contributor** on the
  Foundry resource (or hub)
- create a **new** one: **Contributor on the resource group** as well

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

The app can reach the telemetry target in two ways:

| Route | Needs |
| --- | --- |
| **Project endpoint** → `telemetry.get_application_insights_connection_string()` | Microsoft Entra ID configured in the application, **and** permission to read the project's connection |
| **Application Insights connection string** | only the string (portal: *Project → Tracing → Manage data source → Connection string*) |

> «Using a project's endpoint requires configuring Microsoft Entra ID in your
> application. **If you don't have Entra ID configured, use the Azure Application
> Insights connection string** as indicated.»

**Feature 006 uses the connection string.** Reading the project's connection is
a **data action**, `Microsoft.CognitiveServices/accounts/AIServices/connections/read`.
The only built-in role that carries it grants the whole Cognitive Services data
plane, which is too broad for one lookup. The connection string is copied from
the Application Insights resource, and the refusal stays in place. Details are in
`genaiops/foundry-block3/README.md` and `foundry-rbac-and-authentication.md` § 1.

---

## 3. What a span contains

GenAI semantic-convention attributes, from Learn's console output:

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

`gen_ai.usage.input_tokens` and `output_tokens` give token consumption per call.
The platform token metrics are the documented source for totals
(`genai-production-monitoring.md` § 4).

The span does not contain the prompt text or the response text.

### Message content is opt-in

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

Learn lists this as *«(Optional) Capture message content»*. Without it, spans
carry durations, token counts, model names and finish reasons, and no message
text. The default protects privacy.

Exam trap: "we see latency and token counts but not the prompts" is fixed by
setting this one environment variable. It is not a bug or a permission problem.

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

The decorator places every model call made inside the function under one parent
span, so business steps appear next to the model calls. Custom attributes link a
call to data the platform does not know about: `call_model.py` records the
prompt file's git revision this way.

### What the portal shows

Per trace: **Trace ID**, start time, duration, status, and **Operations** (the
number of spans). Opening a trace shows the execution timeline, input and output
per operation, timing, errors, and custom attributes.

---

## 4. Reading traces back

> «Make sure you have the **Log Analytics Reader** role assigned in your
> Application Insights resource. If the underlying Log Analytics tables are
> **protected**, also assign the **Privileged Monitoring Data Reader** role.»

Both are **Azure Monitor** roles on the Application Insights resource. Writing a
trace and reading it back are governed by two different services.

Feature 006's plan predicted the opposite of what happened. It expected the query
to need `Log Analytics Reader` and inference to need nothing. The Log Analytics
query worked under Owner, because it is a control-plane action. Inference failed,
because it is a data action. Learn's roles apply to the general case; an Owner
already holds the control-plane actions the query needs.

The read must happen in a **separate process**. A trace visible only in the
terminal that produced it does not prove observability. `query_trace.py` does
this read.

---

## 5. Tracing without Azure

Two documented paths, both free.

### Console exporter, for CI

> «Traces can be sent to the console and captured by your CI/CD tool for further
> analysis.» Learn recommends it for «**unit tests or integration tests** in your
> application **using an automated CI/CD pipeline**».

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)
```

`OpenAIInstrumentor().instrument()` stays the same; only the exporter changes.
CI can therefore trace without Application Insights.

The sample uses **`SimpleSpanProcessor`**, which exports each span when it ends.
§ 7 shows why this matters.

### Foundry Toolkit, for local development

A local OTLP-compatible collector in VS Code, «perfect for development and
debugging without needing cloud access». It supports the OpenAI SDK and other
frameworks through OpenTelemetry.

---

## 6. Network requirements

If Foundry uses virtual network injection and outbound traffic passes a
firewall, tracing needs two FQDNs on the allowlist, listed under *Evaluations &
Traces*:

- `*.blob.core.windows.net`
- `settings.sdk.monitor.azure.com`

Learn: «Used for the evaluators catalogue and for **sending results to the linked
Application Insights resource**.» Without them, telemetry from an isolated
deployment never leaves the network. The rest of the outbound rules are in
`network-isolation.md`.

---

## 7. The batch processor loses spans at exit

**Measured here on 2026-08-19. Learn does not document this.**

The first version of `call_model.py` let the OpenTelemetry **batch** processor
export at interpreter exit. The first call was retrieved, so tracing seemed to
work. A second call never arrived: three hours later the workspace still held one
record, so the span was lost.

A batch processor queues spans and exports them on a timer. A short-lived CLI
exits before the timer fires, and the queued spans are lost. The fix is to flush
explicitly before exit.

- The success criterion required **two** records. With one, a mechanism that
  works about half the time would have shipped.
- Learn's console sample uses `SimpleSpanProcessor`. For a short-lived process
  it is the safer choice.

**Observed ingestion lag: 2 to 3 minutes.** A record still missing after that is
lost.

---

## 7b. Sampling: the SDK default drops spans

**Read on 2026-09-22, after this gap cost feature 007 two days (F6).** As in § 7,
the cause is a default designed for long-running services, applied to a
short-lived CLI.

### Two samplers in two places

| | Where it runs | Default | How to check it |
| --- | --- | --- | --- |
| **SDK sampling** | in your process, at span creation | **on** | read the SDK; `az` cannot see it |
| **Ingestion sampling** | Azure, at the ingestion endpoint | off | `samplingPercentage: null` on the component |

`samplingPercentage: null` shows only that **ingestion** sampling is off. The two
share a name and run in different places, which makes a likely exam trap.

> «The Application Insights OpenTelemetry distros include a **default sampler**.
> The specific sampler and its rate depend on the language and distro version.»

Learn marks ingestion sampling «not recommended»: «It drops data at the Azure
Monitor ingestion point and offers no control over which traces and spans are
retained.» Use it only when you cannot change the application.

### What is sampled

> - «Sampling decisions apply to **traces** (spans).»
> - «**Logs** that belong to unsampled traces are dropped by default.»
> - «**Metrics** are never sampled.»

The last rule explains why F6 looked like a broken ingestion pipeline:
`AppMetrics` kept arriving while `AppDependencies` stayed empty, from the same
process, connection string and minute. Arriving metrics prove the connection
works. They say nothing about spans.

### Checking whether you are sampled

Learn's query reads the retained percentage from `itemCount`:

```kusto
union requests,dependencies,pageViews,browserTimings,exceptions,traces
| where timestamp > ago(1d)
| summarize RetainedPercentage = 100/avg(itemCount) by bin(timestamp, 1h), itemType
```

> «If you see that `RetainedPercentage` for any type is less than 100, then that
> type of telemetry is being sampled.»

**F6 never ran this query.** It would have found in one step what took two days
of elimination. It reports per `itemType`, so it also shows the metrics and
dependencies split.

### Configuring it

Environment variables **override code**:

```bash
export OTEL_TRACES_SAMPLER="microsoft.fixed_percentage"   # or microsoft.rate_limited
export OTEL_TRACES_SAMPLER_ARG=0.1                        # ~10%; or traces/sec
```

```python
configure_azure_monitor(connection_string=..., sampling_ratio=1.0)  # keep everything
```

`always_on` is also a valid sampler type. For a study harness or any short-lived
CLI, **keep 100%**: the volume is a few spans, and every record must be
retrievable.

### The Python default and its startup behaviour

Since **`azure-monitor-opentelemetry` 1.8.6 (2026-02-05)** the Python default is
rate-limited sampling. Learn states it on the Python tab of *Configuring
OpenTelemetry in Application Insights* (§ Enable sampling):

> «Starting from version 1.8.6, **rate-limited sampling is the default**.»
> «If you don't set any environment variables or provide either `sampling_ratio`
> or `traces_per_second`, `configure_azure_monitor()` uses **RateLimitedSampler**
> by default.»

The package changelog gives the rate, which Learn does not:

> «The default sampling behavior has been changed from ApplicationInsightsSampler
> with 100% sampling (all traces sampled) to **RateLimitedSampler with 5.0
> traces per second**.»

Neither source describes what happens at process start. This part is measured
here.

At 5 traces per second, a single span looks safe. The limiter is adaptive: it
computes its percentage from an exponentially decayed window that **starts at
zero**, with a 0.1 s adaptation constant. Measured against 1.8.9:

| Process age at first span | Sampling percentage |
| --- | --- |
| 0 ms | **0%** |
| 100 ms | 50% |
| ≥ 500 ms | 100% |

The sampler drops the most spans right after startup. A CLI that configures,
calls and exits runs entirely in that window. Twelve spans emitted back to back:
1 recorded with the default, 12 with `sampling_ratio=1.0`.

The drop happens at span creation, so the span is never queued or exported.
**`force_flush()` still returns `True`**, because there is nothing to flush, and
the ingestion endpoint still answers `Items accepted` for the telemetry that was
sent. All three signals are green and the span does not exist. See
`specs/007-genai-eval-observability/findings.md` § F6.

Two rules:

- **A pinned version range does not pin behaviour.** `>=1.6,<2.0` accepted a
  documented change of default with no commit in this repository.
- **Check the SDK's sampler as well as the resource's.** They share a name and
  answer different questions.

---

## 8. What this note would cost to verify

**§§ 2 to 5 are already paid for or free.** The spans, the retrieval and the
flush bug used about 1,300 tokens on a `GlobalStandard` deployment, which bills
nothing at rest. Application Insights bills per GB ingested; a few spans do not
register.

The standing cost is the **Log Analytics workspace**, which keeps the spans after
the process exits and makes the retrieval possible. It was deleted with
`rg-ai300-foundry`.

Not tested, and free: **the console exporter path** (§ 5). It needs no Azure
resource and would turn the CI path from documented to measured.

---

## Sources

- [View trace results for AI applications using OpenAI SDK](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/trace-application): read 2026-08-21 via `/azure/ai-foundry/concepts/trace`, which redirects here; §§ 1 to 5
- [How to configure network isolation for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link): read 2026-08-21; § 6
- [Tracing in Foundry Toolkit](https://code.visualstudio.com/docs/intelligentapps/tracing): referenced by the Learn page; § 5
- [Sampling in Azure Application Insights with OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling): read 2026-09-22; § 7b, metrics are not sampled, the `RetainedPercentage` query
- [Configuring OpenTelemetry in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration#enable-sampling): read 2026-09-22, reread 2026-09-25 (ms.date 2026-06-19); § 7b, sampler environment variables and the Python default
- [azure-monitor-opentelemetry CHANGELOG, 1.8.6](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/monitor/azure-monitor-opentelemetry/CHANGELOG.md): read 2026-09-22; § 7b, the default rate of 5.0 traces per second
- `foundry-rbac-and-authentication.md` § 1: why reading a connection is a data action
- `network-isolation.md`: outbound rules for § 6
- `genaiops/foundry-block3/call_model.py`, `query_trace.py`, `README.md`: § 7
- `specs/007-genai-eval-observability/findings.md` § F6: § 7b
