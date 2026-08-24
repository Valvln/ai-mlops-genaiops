# Prompt and agent versioning — what Foundry versions, and what only Git versions

**Status: half built, and the built half is the smaller half.** Feature 006
versioned a prompt as a file — `genaiops/foundry-block3/prompts/hello-domain3.prompty`
— and `call_model.py` resolves its git revision before each call and attaches it
to the span. **No agent has ever been created in this subscription, and no
prompt flow has ever been authored**, so agent versioning and variants below are
read, not observed.

Every behavioural claim comes from the Microsoft Learn pages and training module
listed under *Sources*, read on **2026-08-21**.

---

## 1. Where a prompt lives in Foundry

A prompt is not a first-class Azure resource. It is a **component of an agent
definition**:

| Component | Purpose |
| --- | --- |
| **Agent definition** | name and metadata, with a version number |
| **System instructions** | *the prompt* — defines behaviour and capabilities |
| **Model selection** | the underlying model powering responses |
| **Tool integrations** | optional connections to external services or data |

> «The system instructions, your prompt, represent **the most frequently changed
> component**. While you rarely modify the model or tools, you continuously
> refine prompts.»

That asymmetry is the whole justification for the topic: the part that changes
hourly is the part with no built-in review, no diff and no author, unless you
give it one.

---

## 2. What Foundry versions on its own

> «Microsoft Foundry creates a new agent version **whenever you create or update
> an agent, whether through the portal interface or the Python SDK**.»

This kills the most common wrong belief — that portal edits are unversioned while
SDK edits are versioned. **Both produce a version.** What you get from the
platform, for free, either way:

- test identical scenarios across versions to measure improvement
- compare responses to the same user questions
- identify regressions where a newer version performs worse
- switch between deployed versions in the portal **and** list them
  programmatically from the SDK, to automate comparison

## 3. What only Git versions

The reason to prefer the SDK is not that it versions and the portal doesn't:

> «The SDK approach enables better version control integration **by storing
> prompts in files that Git can track**.»

Foundry versions **the agent**. Git versions **the text**, with a diff, an
author, a message and a review. Those are different artefacts answering different
questions, and an exam stem that says "we need to know *why* the prompt changed"
is asking for the second one.

The separation the module recommends:

- **prompt files** (`v1_instructions.txt`, `v2_instructions.txt`) — the system
  instructions
- **deployment script** (`trail_guide_agent.py`) — reads the prompt and deploys
  it
- **version control** — tracks changes to both

```python
# Read prompt from version-controlled file
with open('prompts/v1_instructions.txt', 'r') as f:
    instructions = f.read().strip()

agent = project_client.agents.create_agent(
    model=os.environ["MODEL_NAME"],
    name=os.environ["AGENT_NAME"],
    instructions=instructions,
)
```

### Three storage strategies, with the trade-off each carries

| Strategy | Learn's assessment |
| --- | --- |
| **Embedded prompts** — strings inside the Python script | «Simple for small teams but **harder to review prompt-only changes**» |
| **Separate files** — `.txt` or `.md` | «Better for **nontechnical reviewers** and clearer version history» |
| **Configuration management** — YAML or JSON with metadata | «Good for **complex deployments with multiple environments**» |

None is declared wrong. The criterion is «your team's technical expertise, review
processes, and deployment complexity».

`hello-domain3.prompty` sits in the third category in form — frontmatter carrying
the deployment name and sampling parameters — and in the second in spirit.

---

## 4. The safe deployment workflow

### Two environments, two contracts

| Environment | Characteristics |
| --- | --- |
| **Development** | safe testing space, representative data, rapid iteration, integration with testing frameworks |
| **Production** | **validated prompts only**, real user interactions, performance monitoring, controlled changes |

> «Development prompts follow the workflow: Idea → Draft → Test → Refine → Test
> Again → Ready for Review. **Production prompts must be thoroughly tested,
> approved through review, have performance baselines, and include rollback
> plans.**»

### Branch naming, as the module states it

```
feature/improve-customer-greeting     # new prompt development
hotfix/fix-greeting-error             # urgent production fixes
experiment/tone-variations            # testing alternative approaches
```

### The five steps

1. **Create a development branch** from an up-to-date `main`
2. **Develop and test locally** — edit, test with sample inputs, document the
   reasoning *for reviewers*, commit incrementally
3. **Prepare for review** — a commit message explaining what changed and why
4. **Open a pull request** — include testing results and performance comparisons
5. **Merge and deploy** — **tag the release version**, deploy, monitor

### The five lifecycle stages

| Stage | Success criterion |
| --- | --- |
| Development | meets functional requirements |
| Validation | meets or exceeds benchmarks |
| Review | team consensus and formal approval |
| Production | stable performance and user satisfaction |
| Monitoring | maintained or improved performance |

> «Each stage builds on the previous one. **Don't skip stages to save time**;
> each provides critical validation that prevents production issues.»

### What to automate, and in what order

Automated testing → performance monitoring → deployment pipelines → **one-click
rollback to previous prompt versions**. The stated order is not arbitrary:
«Start with automated testing and gradually add monitoring and deployment
automation.»

---

## 5. Variants in prompt flow

> «A variant refers to **a specific version of a tool node that has distinct
> settings**. Currently, variants are supported **only in the LLM tool**… a new
> variant can represent either a **different prompt content** or **different
> connection settings**.»

The mental model: a variant is not a copy of the flow and not a Git tag. It is an
alternative configuration of **one node**, held inside the flow.

| | Prompt | Connection settings |
| --- | --- | --- |
| Variant 0 (**default**) | `Summary: {{input sentences}}` | Temperature = 1 |
| Variant 1 | `Summary: {{input sentences}}` | Temperature = 0.7 |
| Variant 2 | `What is the main point of this article? {{input sentences}}` | Temperature = 1 |

`variant_0` is the existing node and is the default; further variants are cloned
from it.

### The rule that makes the comparison valid

> «Each time you can only select **one LLM node with variants to run** while
> other LLM nodes will use the default variant.»

> «To test how different variants work for each node in a flow, you need to run a
> batch run for each node with variants **one by one**… This follows the rule of
> the **controlled experiment**, which means that you only change one thing at a
> time and keep everything else the same.»

Eyeballing a single row is explicitly called insufficient — «it can't reflect the
complexity and diversity of real-world data, meanwhile the output isn't
measurable». The documented sequence is: prepare a representative dataset with
ground truth → batch run one node's variants → evaluate with a metric →
**visualize outputs side by side** → set the winner as the node's default
variant → repeat for the next node.

---

## 6. ⚠️ Prompt flow is being retired

> «Prompt flow in Microsoft Foundry and Azure Machine Learning **will be retired
> on April 20, 2027**. Prompt flow is **no longer recommended for new
> development**. Migrate existing Prompt flow applications and deployments to
> **Microsoft Agent Framework** before the retirement date.»

Already true today, not just in 2027:

- **Container images no longer receive updates, including security and package
  updates** — `promptflow-runtime`, `promptflow-runtime-stable`,
  `promptflow-python`
- After the date: the web authoring experience in Foundry and Azure ML, the VS
  Code extensions and the container images all stop being supported
- Prompt flow is **hub-only**: «This article provides legacy support for
  **hub-based projects**. It will not work for **Foundry projects**.»

So variants are worth knowing as **exam vocabulary and as a design pattern**
— one node, one variable, a measured comparison — and are not worth building on.
The pattern outlives the product: it is the same controlled-experiment discipline
as an A/B evaluation, and Domain 5 asks for it again under the RAG heading.

**For this repository the practical consequence is that the hub path stays
closed.** `foundry-cost-model.md` § 6 recommended against a hub on cost grounds;
prompt flow's retirement removes the last capability that might have argued for
one at study scale.

---

## 7. What this note would cost to verify

**Prompt versioning in Git: free, and already done.** Files, diffs, tags,
branches. Nothing about it is Azure-specific — `foundry-cost-model.md` § 5 says so
explicitly.

**Agent versioning: cheap and genuinely untested here.** Creating an agent,
updating its instructions three times and listing the versions costs the tokens
of a handful of calls against the existing `GlobalStandard` deployment — cents at
most — and would convert § 2 from read to observed. It needs Entra auth (the
Agents service **does not accept API keys**, see
`foundry-rbac-and-authentication.md` § 2) and `Foundry User` on the account.

This is the strongest candidate lab left in Domain 3, because § 2 is the section
most likely to be examined and is currently the least verified.

**Prompt flow variants: not worth building.** They need a hub, the hub drags
dependencies that bill at rest (`foundry-cost-model.md` § 1b), and the product
retires in April 2027.

---

## Sources

- [Manage prompts for agents in Microsoft Foundry with GitHub](https://learn.microsoft.com/en-us/training/modules/prompt-versioning-genaiops/) — read 2026-08-21; unit 3 (*Understand Microsoft Foundry agents and prompt versioning*) for §§ 1–3, unit 5 (*Develop safe prompt deployment workflows*) for § 4
- [Tune prompts using variants (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/flow-tune-prompts-using-variants) — read 2026-08-21; §§ 5–6, including the retirement notice
- `foundry-cost-model.md` § 1b, § 5, § 6 — why the hub path stays closed
- `foundry-rbac-and-authentication.md` § 2 — why the Agents service needs Entra
- `genaiops/foundry-block3/prompts/hello-domain3.prompty`, `call_model.py` — the built half
