# Monitoring generative AI in production: dashboard, latency, tokens, cost

**Status: mostly documented, not built.** The repository has no production
traffic, no agent, and has never opened the Agent Monitoring Dashboard or an
Azure Monitor metrics chart for a model deployment. What it has measured is
adjacent: a rate limit that looked like a quota (F3), and a token counter built
on a trace store that lost spans (F6) and later counted failed calls (F9).

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-09-25**. Exam objectives: *Examine continuous monitoring in
Foundry*, *Monitor performance metrics, including latency, throughput, and
response times*, *Track and optimize cost metrics, including token consumption
and resource usage*. Tracing and logging are in `genai-tracing.md`.

---

## 1. The Agent Monitoring Dashboard

The agent's **Monitor** tab in the new Foundry portal (preview). It reads
telemetry from the **Application Insights resource connected to the project**;
without that connection it has nothing to show.

| Metric | Learn's rule of thumb |
| --- | --- |
| Token usage | high usage suggests verbose prompts or responses |
| Latency | **above 10 seconds** suggests throttling, complex tool calls or network issues |
| Run success rate | **below 95%** warrants investigation |
| Evaluation metrics | scores from evaluators on **sampled** agent outputs |
| Red teaming results | outcomes of scheduled scans, if enabled |

Settings on the same tab: **recurring evaluations**, **red team scans**,
**alerts** (latency, token usage, evaluation scores, red team findings).

> «Monitoring data is stored in the connected Application Insights resource.
> **Retention and billing follow your Application Insights configuration.**»

Permissions to see it: an RBAC role on the Application Insights resource, and
for log-based views **Log Analytics Reader** on the workspace, plus
**Privileged Monitoring Data Reader** if the tables are protected.

Agents running outside Foundry can appear here too: register them in the
Foundry Control Plane, instrument them with the **OpenTelemetry GenAI semantic
conventions**, and send telemetry to the project's Application Insights.

Troubleshooting "empty charts": no recent traffic, a time range that excludes
the data, or ingestion delay.

---

## 2. Azure Monitor platform metrics for model deployments

> «Azure Monitor collects metrics from Foundry Models automatically. **No
> configuration is required.**»

Platform metrics live in the Azure Monitor time-series store, support near
real-time alerting, and are visible in the deployment's **Metrics** tab in the
Foundry portal or in Metrics Explorer. Viewing them needs **Monitoring
Reader**.

The newer **Models** category covers every model in the resource (Azure OpenAI,
DeepSeek, Phi). The older **Azure OpenAI** category covers Azure OpenAI models
only. Learn recommends switching to Models.

| Group | Metric | What it is |
| --- | --- | --- |
| Requests | `ModelRequests` | calls to the inference API; split by `StatusCode` to see 429s and 5xx |
| Requests | `ModelAvailabilityRate` | (total calls − server errors) / total calls; server errors are HTTP ≥ 500 |
| Latency | `TimeToResponse` | time to the **first** response chunk, measured at the API gateway |
| Latency | `NormalizedTimeBetweenTokens` | token generation rate on streaming requests |
| Usage | `InputTokens`, `OutputTokens`, `TotalTokens` | tokens in, out, and their sum |
| Usage | `TokensCacheMatchRate` | share of prompt tokens served from cache (PTU) |
| Usage | `ProvisionedUtilization` | PTU consumed / PTU deployed; **at ≥ 100% calls return 429** |

`TimeToResponse` excludes client-side latency: «Refer to your own logging for
optimal latency tracking.»

### Resource logs need a diagnostic setting

Metrics are automatic. **Logs are not**:

> «Logs are generated automatically, but you must route them to Azure Monitor
> logs to save or query by configuring a **diagnostic setting**.»

Categories: **RequestResponse** (every inference request, status, latency),
**Trace**, **Audit** (deployments, configuration, access control). Configuring
the setting needs **Monitoring Contributor**. Collecting into Log Analytics
costs ingestion, so Learn says to collect only the categories you need. Data
can take up to 15 minutes to appear.

---

## 3. Latency and throughput

### Two different things

- **Throughput**: system level, in tokens per minute (TPM) and requests per
  minute. On a standard deployment the quota «only determines the admission
  logic for calls… and doesn't directly enforce throughput».
- **Latency**: per call, the time to get a response back.

### The latency formula

> **TTLT = TTFT + (TBT × Tokens Generated)**

| Term | Metric (Azure OpenAI category) |
| --- | --- |
| TTLT, time to last token | Time to Last Byte, `AzureOpenAITTLTInMS` |
| TTFT, time to first token | Time to Response, `AzureOpenAITimeToResponse` |
| TBT, time between tokens | Time Between Tokens, `AzureOpenAINormalizedTBTInMS` |

`Normalized Time to First Byte` divides first-byte latency by prompt tokens; use
it to compare efficiency across prompt sizes, **not** to diagnose absolute
latency.

The rule Learn repeats:

> «**Always pair a latency metric with a token count metric.** A 5-second TTLT
> that generates 2,000 tokens is very different from a 5-second TTLT that
> generates 50 tokens. Latency without token context isn't actionable.»

If TTLT and generated tokens rise together, that is expected behaviour. If TTLT
rises alone, check capacity: `ProvisionedManagedUtilizationV2` on PTU, or
requests and 429s on pay-as-you-go.

### What moves latency

- **Output tokens dominate**: «each prompt token adds little time compared to
  each incremental token generated». Lower `max_tokens`, add stop sequences,
  keep `n` at 1.
- **Streaming** lowers time to first token and leaves total time unchanged:
  «It doesn't change the time to get all the tokens, but it reduces the time
  for first response.»
- **Content filtering** adds latency.
- **Mixing workloads** on one deployment hurts latency and cache hit rate;
  separate deployments per workload.
- **Model choice**.

### Measuring throughput

Calls per minute from the requests metric split by `ModelDeploymentName`, and
total tokens per minute from **Processed Inference Tokens** (prompt plus
generated). To size a deployment from history, read **Processed Prompt
Tokens** and **Generated Completion Tokens** over a multi-week window at
1-minute granularity; this ignores prompt caching, so it is a conservative
estimate.

---

## 4. Cost

Three sources, three purposes:

| Source | Gives | Delay |
| --- | --- | --- |
| Token metrics (`InputTokens`, `OutputTokens`, `TotalTokens`) | consumption by deployment, model, version | near real time |
| **Azure Cost Management → Cost analysis** | actual post-consumption **charges**, per deployment, input/output token cost | **about five hours** |
| Token counts in the API response `usage` object | per-request prompt, completion and total tokens | immediate, in your code |

The Foundry portal's deployment **Metrics** tab links straight to Cost
Management; viewing cost needs at least read access to the billing account data.

Metrics are also the reliable base for alerts because they are **never
sampled**. Learn's sampling guidance: «Metrics aren't sampled. Use them to
reliably alert on key signals», and «Any sampling reduces accuracy, so alert on
OpenTelemetry metrics, which are unaffected by sampling» (`genai-tracing.md`
§ 7b).

Cost levers documented in these pages: fewer generated tokens (§ 3), prompt
caching on PTU, turning off playground evaluations that bill by default
(`genai-evaluation-workflows.md` § 5), collecting only the diagnostic log
categories you need (§ 2), and not running CI evaluation on every commit.

---

## 5. What this repository measured, and what it did not

**Measured:**

- **F3.** A `GlobalStandard` deployment with `capacity: 1` allowed **one request
  per minute**. The limit was read from `properties.rateLimits`, and raising
  capacity changed no price. This is Learn's throughput point in practice: on a
  standard deployment capacity sets admission, and costs nothing at rest.
- **F6 and F9.** `--count-invocations` counted model calls from `genaiops.*`
  spans in Application Insights. With the SDK's default sampler it read **3 for
  about 13 calls**; after the fix it read **10 for 8**, because failed judge
  calls are exported as spans. The counter failed first toward under-reporting,
  then toward over-reporting.

**Where this repository diverges from Learn:** the repository derived its cost
guardrail from spans, on the principle that a second source of truth drifts.
Learn's documented sources for consumption are the platform **token metrics**,
collected automatically and never sampled, and **Cost Management** for
charges. A span count is subject to SDK sampling (F6) and to whatever the
application chooses to emit (F9); a platform metric is subject to neither.

**Not measured:** the Agent Monitoring Dashboard, any Azure Monitor metric for a
model deployment, any latency metric, diagnostic settings for model logs,
Cost Management at deployment grain, any alert.

---

## 6. What this note would cost to verify

**Metrics cost nothing extra**: they are collected automatically for any
deployment that receives traffic. The next time `infra/foundry.bicep` is
deployed, opening the deployment's Metrics tab after the existing
`call_model.py` runs would show `ModelRequests` and `TotalTokens`, and
comparing them to `--count-invocations` would test § 5's divergence directly.
A diagnostic setting sending `RequestResponse` to the existing Log Analytics
workspace costs ingestion only, a few kilobytes for a handful of calls. The
dashboard needs an agent, which this repository does not have.

---

## Sources

- [Monitor agents with the Agent Monitoring Dashboard](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard): read 2026-09-25 (ms.date 2026-09-03); § 1
- [Monitor model deployments in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models): read 2026-09-25 (ms.date 2026-09-08); § 2, Cost Management delay in § 4
- [Azure OpenAI performance and latency](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/latency): read 2026-09-25 (ms.date 2026-05-14); § 3
- [Observability in generative AI](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability): read 2026-09-25 (ms.date 2026-07-31); monitoring and alerts
- [Sampling in Azure Application Insights with OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling): read 2026-09-25 (ms.date 2025-12-10); metrics are not sampled
- [Configuring OpenTelemetry in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration#enable-sampling): read 2026-09-25 (ms.date 2026-06-19); alert on metrics
- `specs/007-genai-eval-observability/findings.md` F3, F6, F9: § 5
