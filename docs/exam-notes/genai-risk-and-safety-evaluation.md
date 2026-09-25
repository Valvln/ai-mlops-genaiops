# Risk and safety for generative AI: safety evaluators, red teaming, guardrails

**Status: documented, not built.** No safety evaluator, red-teaming scan or
custom guardrail has run in this repository. Feature 007 used the default
guardrail without inspecting it. The tracker files this topic as theory.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-09-25**. Exam objective: *Configure risk and safety evaluations
for harmful content detection*.

Three mechanisms cover this topic, at three different moments:

| Mechanism | When it runs | What it does |
| --- | --- | --- |
| **Safety evaluators** | on a dataset or on sampled traffic, after the response exists | measure and report |
| **AI Red Teaming Agent** | before deployment, or on a schedule after | generate attacks, then measure with the safety evaluators |
| **Guardrails** (content filters) | inline, on every request | annotate or block |

Evaluators and red teaming **measure**. Guardrails **intervene**.

---

## 1. The safety evaluators

| Evaluator | Detects | Targets | Required inputs |
| --- | --- | --- | --- |
| `builtin.hate_unfairness` | hate toward, or unfair representation of, social groups | model and agents | `query`, `response` |
| `builtin.sexual` | sexual content | model and agents | `query`, `response` |
| `builtin.violence` | violent content | model and agents | `query`, `response` |
| `builtin.self_harm` | self-harm content | model and agents | `query`, `response` |
| `builtin.protected_material` | copyrighted text (lyrics, recipes, articles) | model and agents | `query`, `response` |
| `builtin.code_vulnerability` | insecure generated code (SQL injection, tar-slip, hardcoded credentials, …) | model and agents | `query`, `response` |
| `builtin.ungrounded_attributes` | ungrounded inferences about emotional state or protected class | model and agents | `query`, `response`, **`context`** |
| `builtin.indirect_attack` (XPIA) | whether the response fell for a jailbreak injected into context | **model only** | `query`, `response` |
| `builtin.prohibited_actions` (preview) | agent actions that violate a user-defined policy | **agents only** | `query`, `response`, `tool_calls` |
| `builtin.sensitive_data_leakage` (preview) | agent exposing financial, personal or health data | **agents only** | `query`, `response`, `tool_calls` |

The two agent-only evaluators are «supported for agent targets only and aren't
available for dataset or model evaluations».

### Who does the judging

> «Risk and safety evaluators use the **hosted Foundry Evaluation service** and
> **don't require a `deployment_name`** initialization parameter. Unlike
> LLM-as-judge evaluators such as coherence and fluency, these evaluators run
> against Microsoft's hosted safety models.»

In the local SDK the same rule appears as: pass `azure_ai_project`, not a
`model_config`. Your own judge deployment plays no part. Protected Material uses
the Azure AI Content Safety Protected Material for Text service.

### ⚠️ The threshold runs the other way

Quality evaluators pass at **score ≥ threshold** on a 1–5 scale, higher is
better. Content-safety evaluators use a **0–7 severity** scale, lower is better:

> «Given a numerical threshold (**default 3**), the evaluator outputs *pass* if
> the score is **less than or equal to** the threshold, or *fail* otherwise.»

| Severity | Range |
| --- | --- |
| Very Low | 0–1 |
| Low | 2–3 |
| Medium | 4–5 |
| High | 6–7 |

So the default of 3 means "pass up to and including Low". The same number, 3, is
the default for both families and means opposite things.

The other safety evaluators are binary: XPIA and Code Vulnerability **fail if
any** subcategory is detected. Ungrounded Attributes returns `true` only when an
emotional state or protected class is detected **and** ungrounded in the
context.

The aggregate over a run is a **defect rate**: the percentage of responses in
which undesired content was detected.

### Region support

Safety evaluators run only in listed regions. The ones that matter here:

| Capability | Regions (selection) |
| --- | --- |
| Hate, sexual, violence, self-harm, XPIA, code vulnerability, ungrounded attributes | Sweden Central, France Central, Germany West Central, Italy North, Norway East, Poland Central, Spain Central, Switzerland North/West, West Europe, East US 2, … |
| Groundedness Pro | **East US 2, Sweden Central** only |
| Protected Material | **East US 2** only |

North Europe, the repository's default region, is **not** on the safety list.
Sweden Central, where feature 007 ran, is.

---

## 2. The AI Red Teaming Agent

Automated adversarial probing, built on Microsoft's open-source **PyRIT**, with
the safety evaluators as the scorer. Three steps: **scan** (simulate attacks),
**evaluate** (score each attack-response pair), **report** (a scorecard by risk
category and attack strategy).

### Attack Success Rate

> «The key metric to assess the risk posture of your AI system is **Attack
> Success Rate (ASR)** which calculates the percentage of successful attacks over
> the number of total attacks.»

Lower ASR is better. ASR is scored by generative models and is
«non-deterministic»; Learn recommends reviewing results before acting and
combining the tool with **human-in-the-loop** analysis.

### How an attack is built

The agent starts from **seed prompts** per risk category. A direct harmful ask
is usually refused by the model's own alignment, so PyRIT **attack strategies**
convert the prompt to slip past it: encodings (Base64, ROT13, Caesar, Atbash,
Morse, Binary, Url), character tricks (Flip, CharSwap, Leetspeak,
UnicodeConfusable, Diacritic, AsciiSmuggler), Jailbreak (user-injected, UPIA),
Indirect Jailbreak (injected into tool output or context, XPIA), Tense (rewrite
into past tense), and multi-turn strategies (**Multi turn**, **Crescendo**:
gradual escalation over turns).

### When to use it

Learn maps it to NIST's Map / Measure / Manage and to four lifecycle points:

- **Design**: choose the safest foundation model
- **Development**: when upgrading a model or fine-tuning
- **Pre-deployment**: before an app or agent goes to production
- **Post-deployment**: **scheduled** red-teaming runs on synthetic adversarial data

### Local and cloud

| | Local | Cloud |
| --- | --- | --- |
| Content risk categories | yes | yes |
| Agentic categories: prohibited actions, sensitive data leakage, task adherence | **no** | **yes, cloud only** |
| Adversarial inputs in results | visible | **redacted** |

Cloud red teaming regions: East US 2, France Central, Sweden Central,
Switzerland West, North Central US. Only **text** scenarios are supported. For
agents: Foundry-hosted prompt and container agents with Azure tool calls are
supported; workflow agents, non-Foundry agents and function tool calls are not.

Learn's recommended environment is a **purple environment**: non-production,
configured with production-like resources.

---

## 3. Guardrails: the inline controls

A **guardrail** is a named collection of **controls**. Each control names a
**risk**, the **intervention points** to scan, and the **action** to take. The
classifiers are Azure AI Content Safety models.

### Risks

Hate, sexual, self-harm, violence (severity-based); **user prompt attacks**
(jailbreak) and **indirect attacks** (Prompt Shields); protected material for
text and for code; groundedness (preview, models only); PII (preview); task
adherence (preview); spotlighting (preview, models only).

### Intervention points

| Point | Models | Agents |
| --- | --- | --- |
| User input | yes | yes |
| Tool call | no | yes (preview) |
| Tool response | no | yes (preview) |
| Output | yes | yes |

### Actions

**Annotate** (models only) or **annotate and block**.

### Severity thresholds for the four content risks

| Setting | Content filtered |
| --- | --- |
| Low | low, medium and high: the strictest configuration |
| Medium | medium and high |
| High | high only |
| Off, or annotate only | nothing blocked; for completions **only for customers approved for modified guardrails** |

Content at the **safe** level is annotated and never filtered, and the safe
level is not configurable.

### The default

> «By default, models are assigned the **Microsoft.DefaultV2** guardrail.»

For text models the default policy sets hate, violence, sexual and self-harm to
**Medium** on **both prompts and completions**: medium and high are filtered,
low and safe pass. Jailbreak detection runs on prompts; protected material for
text and for code runs on completions.

### What the caller sees

- A filtered **prompt** returns **HTTP 400** with error code `content_filter`.
- A filtered **completion** returns HTTP 200 with `finish_reason:
  "content_filter"`; a non-streaming call returns no content.
- If the filtering system is unavailable, the request **still completes,
  unfiltered**, and `content_filter_results` carries an error. Learn's best
  practice is to check `finish_reason` and that error object on every response.

### Agent override

> «Risks are detected in an agent based on the guardrail it's assigned, not the
> guardrail of its underlying model. **The agentic guardrail fully overrides the
> model's guardrail.**»

An agent with no guardrail of its own inherits its model deployment's. An agent
whose guardrail omits tool-call controls has its tool calls **unscanned**, even
if the model's guardrail is stricter.

Creating or editing guardrails requires **Foundry Account Owner**.

### Guardrails cost latency

Learn's latency guide lists content filtering as a latency factor and suggests
modified filtering for low-risk workloads, subject to the approval above.

---

## 4. What this repository measured, and what it did not

**Measured:** nothing on this topic. Feature 007 called `gpt-4.1-mini` under
the default guardrail and never read its configuration, its annotations, or a
filtered response.

**Not measured:** every evaluator in § 1, every red-teaming capability in § 2,
every guardrail setting in § 3.

**What the repository's own findings suggest for this topic:**

- F5 showed an LLM-judge threshold passing a defect. The safety threshold has
  the opposite direction (§ 1), so the F5 intuition "raise the threshold to be
  stricter" is **wrong** here: stricter means a **lower** severity threshold.
- A red-teaming ASR is a score from a generative model. The same caution F5
  applies to a groundedness verdict applies to it: read the per-item results.

---

## 5. What this note would cost to verify

Safety evaluators bill on consumption under Foundry Observability pricing, and
need a project in a supported region: Sweden Central works. A ten-row dataset
through four content evaluators would cost cents. Cloud red teaming runs in
Sweden Central as well; its cost scales with the number of attack objectives
and strategies, so a scan limited to one risk category and two strategies is
the cheap version. Guardrail configuration is free; testing it costs the tokens
of the requests you send. None of it leaves anything billing when idle.

---

## Sources

- [Risk and safety evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/risk-safety-evaluators): read 2026-09-25 (ms.date 2026-04-02); § 1
- [AI Red Teaming Agent](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent): read 2026-09-25 (ms.date 2026-08-19); § 2
- [Rate limits, region support, and enterprise features for evaluation](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network): read 2026-09-25 (ms.date 2026-04-03); region tables
- [Guardrails and controls overview](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview): read 2026-09-25 (ms.date 2026-07-31); § 3
- [Default Guardrail policies for Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/default-safety-policies): read 2026-09-25 (ms.date 2026-05-31); the Medium defaults
- [Content filtering for Foundry Models (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/foundry-models/concepts/content-filter): read 2026-09-25 (ms.date 2026-08-04); configurability table, HTTP 400, `finish_reason`, unavailable filter
- [Azure OpenAI performance and latency](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/latency): read 2026-09-25 (ms.date 2026-05-14); content filtering as a latency factor
- [Local evaluation with the Azure AI Evaluation SDK (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/evaluate-sdk): read 2026-09-25; `azure_ai_project` for safety evaluators
- [Observability in generative AI](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability): read 2026-09-25 (ms.date 2026-07-31); pricing
