# Quality evaluators for generative AI: the catalogue, LLM-as-judge, and thresholds

**Status: two evaluators exercised, locally.** Feature 007 ran `GroundednessEvaluator`
and `RelevanceEvaluator` from the `azure-ai-evaluation` SDK on a laptop, with
`gpt-4.1-mini` as the judge, and wrote each verdict to a span
(`qa-observability/foundry-block4/evaluate_call.py`). Everything else in this
note, including cloud evaluation, custom evaluators and agent evaluators, is
documented and has not been built here.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-09-25**. Exam objective: *Implement AI quality metrics, including
groundedness, relevance, coherence, and fluency*, and *Create test datasets and
data mapping*.

---

## 1. The built-in catalogue

Learn groups the built-in evaluators in seven families:

| Family | Evaluators | Needs a judge deployment? | Needs ground truth? |
| --- | --- | --- | --- |
| General purpose | Coherence, Fluency | yes | no |
| Textual similarity | Similarity (AI-assisted), F1, BLEU, GLEU, ROUGE, METEOR | Similarity only | **yes, all** |
| RAG | Retrieval, Document Retrieval, Groundedness, Groundedness Pro, Relevance, Response Completeness | yes, except Document Retrieval and Groundedness Pro | Document Retrieval and Response Completeness |
| Risk and safety | see `genai-risk-and-safety-evaluation.md` | no: hosted by the Foundry evaluation service | no |
| Agent | Task Adherence, Task Completion, Intent Resolution, Tool Call Accuracy, Tool Selection, Tool Input Accuracy, Tool Output Utilization, Tool Call Success, Task Navigation Efficiency, Customer Satisfaction, Quality Grader | yes | Task Navigation Efficiency compares against an expected path |
| Rubric (preview) | Rubric: weighted custom criteria, score normalised to 0–1 | yes | no |
| Azure OpenAI graders | Model Labeler, String Checker, Text Similarity, Model Scorer | depends on grader | Text Similarity |

Learn's combinations, worth memorising as the default answer to "which evaluators
for this app":

- **RAG**: Retrieval + Groundedness + Relevance + Content Safety
- **Agent**: Tool Call Accuracy + Task Adherence + Intent Resolution + Rubric + Content Safety
- **Translation**: BLEU + METEOR + Fluency + Coherence
- **All applications**: add Hate and Unfairness, Sexual, Violence, Self-Harm

The local SDK also ships two **composite** evaluators: `QAEvaluator` (groundedness,
relevance, coherence, fluency, similarity, F1) and `ContentSafetyEvaluator`
(violence, sexual, self-harm, hate and unfairness).

---

## 2. What each quality metric measures

| Evaluator | Measures | Required inputs |
| --- | --- | --- |
| Coherence | logical flow and organisation of ideas | `query`, `response` |
| Fluency | grammar and readability, independent of content | `response` |
| Relevance | how accurately and completely the response addresses the query | `query`, `response` |
| Groundedness | alignment with the given context **without fabricating content** | `response`, `context` (optional, recommended); `query` optional |
| Groundedness Pro (preview) | strict consistency with the context, via Azure AI Content Safety | `query`, `response`, `context` |
| Response Completeness (preview) | coverage of the expected information in the ground truth | `ground_truth`, `response` |
| Retrieval | relevance of retrieved chunks to the query, judged by an LLM | `query`, `context` |

### Precision and recall

Learn states the pairing directly:

> «Groundedness focuses on the **precision** aspect of the response. It doesn't
> contain content outside of the grounding context.»
> «Response completeness focuses on the **recall** aspect of the response. It
> doesn't miss critical information compared to the expected response or ground
> truth.»

So "the answer invents something" is a groundedness failure, and "the answer
leaves out something the reference contains" is a completeness failure. Only
completeness needs a ground truth.

Coherence and fluency measure writing quality «**independent of factual
correctness**». A fluent fabrication scores well on both.

### Process and system evaluation

- **System evaluation** scores the final response: Groundedness, Groundedness
  Pro, Relevance, Response Completeness.
- **Process evaluation** scores the retrieval step: Retrieval (no labels, LLM
  judge) and Document Retrieval (labels required). Covered in
  `rag-retrieval-evaluation.md`.

---

## 3. LLM-as-judge: scale, threshold, output

The AI-assisted quality evaluators use a judge model you deploy. The output
contract:

> «These evaluators return scores on a **1-5 Likert scale** (1 = very poor, 5 =
> excellent). **The default pass threshold is 3. Scores at or above the threshold
> are considered passing.**»

```json
{ "name": "Groundedness", "metric": "groundedness", "score": 4,
  "label": "pass", "reason": "…", "threshold": 3, "passed": true }
```

Three consequences:

- A score of **3 passes** at the default threshold. The comparison is `>=`.
- The threshold is a parameter of the evaluator, and the verdict is a function
  of score **and** threshold. A result without its threshold cannot be read.
- The `reason` field is the judge's chain-of-thought explanation. The local SDK
  caps judge generation at 800 tokens for most evaluators, 1,600 for Retrieval
  and 3,000 for Tool Call Accuracy, so reasoning costs tokens on every call.

**Groundedness Pro is the exception**: it runs on the Azure AI Content Safety
service, needs no judge deployment, and returns a boolean `passed` with no
numeric score. Learn describes it as the choice when «you want a **strict**
groundedness definition».

### The judge model

> «For LLM-as-judge evaluators, you can use Azure OpenAI or OpenAI reasoning and
> non-reasoning models for the LLM judge. For the best balance of performance and
> cost, use `gpt-5-mini`.»

The classic local-SDK page still lists `gpt-35-turbo` through `gpt-4o-mini` and
recommends GPT models that are not in preview. The new page is the current one.

### Stated limits of the judge

- Scoring reliability «might vary for very short responses (under approximately
  20 tokens)».
- Coherence and fluency «currently support English-language responses».
- Each evaluation call incurs model inference cost.
- The quality prompts are open source; Learn recommends customising the
  definitions and rubrics to your scenario, which is what a custom prompt-based
  evaluator does (§ 6).

---

## 4. Test datasets

A test dataset row can carry four fields, depending on the evaluators:

- **query**: what was sent to the application
- **response**: what the application returned
- **context**: the grounding documents
- **ground truth**: the reference answer written by a person

Format: **JSONL**. The local `evaluate()` API accepts only JSONL; cloud
evaluation accepts JSONL or CSV.

Two shapes:

- **Single turn**: one `query` and `response` per line.
- **Conversation**: a `messages` array in OpenAI message format. Evaluated per
  turn and averaged, unless the evaluator supports `evaluation_level="conversation"`.

A conversation trap stated by Learn: if a turn's `context` is `null` or
missing, «the evaluator interprets the turn as an empty string instead of
failing with an error, **which might lead to misleading results**». Validate the
data before trusting the score.

Evaluation levels: `turn` (default) or `conversation`. **All evaluators in one
run must support the level you set**; they cannot be mixed.

Service limits for a batch evaluation run: **2 MB per row**, **100,000 rows**.

---

## 5. Data mapping: two syntaxes

The dataset's column names rarely match the evaluator's parameter names. A data
mapping binds them. The syntax depends on the SDK.

| | Cloud evaluation (`azure-ai-projects`, new Foundry) | Local `evaluate()` (`azure-ai-evaluation`, Foundry classic) |
| --- | --- | --- |
| Dataset field | `{{item.query}}` | `${data.query}` |
| Output generated during the run | `{{sample.output_text}}` (model target), `{{sample.output_items}}` (agent) | `${outputs.response}` (from `target=`) |
| Where it goes | `data_mapping` in each testing criterion | `evaluator_config[name]["column_mapping"]`; the key `"default"` applies to all evaluators |

The local SDK also requires fixed keyword names in the `evaluators` dict
(`"groundedness"`, `"relevance"`, `"violence"`, …) for results to render in the
Foundry portal.

---

## 6. Custom evaluators

Three types:

| | Code-based | Prompt-based | Endpoint-based |
| --- | --- | --- | --- |
| How | Python `grade(sample, item)` | a judge prompt | your HTTP endpoint |
| Best for | rules, keywords, format, length | subjective quality, tone | proprietary models, network access |
| Score | float **0.0 to 1.0**, higher is better | ordinal, continuous or binary, range you define | your JSON, standard result schema |
| Required init parameters | `pass_threshold` **and** `deployment_name` | `deployment_name` and `threshold` | connection name |

Constraints of the code-based sandbox: under 256 KB of code, **2 minutes** per
grading call, **no network access**, 2 GB memory, 1 GB disk, 2 cores, a fixed
package list (`numpy`, `pandas`, `scikit-learn`, `nltk`, `rouge-score`, …).

> «If the `grade()` function raises an exception or times out, the service
> **records that item's result as `0.0`** and marks it as an error in the
> evaluation report.»

`deployment_name` is required even for code-based evaluators, which call no
model: «the service API schema requires `deployment_name` for evaluation-run
orchestration».

Endpoint evaluators must answer within **30 seconds**. On failure they return
`status: "error"`, and the schema sets `score` and `passed` to null.

Custom evaluators are registered in the project's **evaluator catalog**, with a
version, and used in runs exactly like built-in ones.

---

## 7. What this repository measured, and what it did not

**Measured (feature 007, findings F4 and F5):**

- The default groundedness threshold of 3 passed a response with three named
  fabrications, at score 4. At threshold 5 the same score failed. Learn
  documents the mechanics exactly (1–5, default 3, `>=`) and says nothing about
  whether 3 suits a gate. The choice of 5 for groundedness is this
  repository's, recorded in `evaluate_call.py`.
- The judge's `reason` named all three fabrications. The failure was the
  threshold, and the judge's description was correct. This matches Learn's
  definition of groundedness as the precision aspect: the judge detected the
  unsupported content and scored it as a partial defect.
- `AzureOpenAIModelConfiguration(credential=...)` is documented and fails
  validation. The credential goes to the evaluator's constructor instead.

**Not measured:** coherence, fluency, Response Completeness, Groundedness Pro,
any textual-similarity metric, any agent evaluator, custom evaluators of any
type, cloud evaluation runs, conversation-level evaluation.

**Where this repository diverges from Learn:**

- The judge is `gpt-4.1-mini`. Learn now recommends `gpt-5-mini`.
- The SDK used is the local `azure-ai-evaluation` path, which Learn now files
  under Foundry (classic). The new-portal path is cloud evaluation through
  `azure-ai-projects` (`genai-evaluation-workflows.md` § 3).
- The strict-groundedness answer Learn documents is **Groundedness Pro**. This
  repository reached strictness by raising the threshold of the LLM-judge
  evaluator.

---

## 8. What this note would cost to verify

Coherence, fluency and relevance on a ten-row JSONL cost the judge's tokens:
at `gpt-4.1-mini` rates a few cents. Groundedness Pro needs a project in **East
US 2 or Sweden Central**; feature 007's region was Sweden Central, so it would
have run there. A code-based custom evaluator runs in the service sandbox and
still needs a deployment name. None of it needs compute that bills while idle.

---

## Sources

- [Built-in evaluators reference](https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators): read 2026-09-25 (ms.date 2026-06-02); § 1, levels in § 4
- [General purpose evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/general-purpose-evaluators): read 2026-09-25 (ms.date 2026-06-02); §§ 2–3, judge model, data mapping
- [RAG evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators): read 2026-09-25 (ms.date 2026-06-02); precision and recall, Groundedness Pro, § 3 output
- [Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators): read 2026-09-25 (ms.date 2026-06-17); § 6
- [Local evaluation with the Azure AI Evaluation SDK (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/evaluate-sdk): read 2026-09-25 (ms.date 2026-02-25); composite evaluators, `${data.x}` mapping, JSONL, conversation trap, judge token caps
- [Rate limits, region support, and enterprise features for evaluation](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network): read 2026-09-25 (ms.date 2026-04-03); row and run limits, Groundedness Pro regions
- `specs/007-genai-eval-observability/findings.md` F4, F5: § 7
- `rag-retrieval-evaluation.md`: process evaluation and Document Retrieval
