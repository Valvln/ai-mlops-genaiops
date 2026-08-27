# Fine-tuning or RAG — the ladder, and the hourly charge that decides it here

**Status: documented, not measured, and deliberately not built.** Read from the
Microsoft Learn pages under *Sources* on **2026-08-27**, before the block 5 plan
freezes.

The short version, which the rest of this note supports: **Learn says start
lower on the ladder, and the price list says this project stops before the top
rung.** Hosting one fine-tuned deployment costs **1,4937 €/hour** — 35,85 €/day —
flat, whether the model is `gpt-4.1-nano` or `gpt-4.1`. That is the same shape of
constraint as provisioned throughput in block 3 (`foundry-cost-model.md`), and it
produces the same decision: **theory, not a lab.**

⚠️ **Documentation trap worth recording.** Both decision pages for this subject
live under `/azure/foundry-classic/` and are stamped *«Applies only to: Foundry
(classic) portal. This article isn't available for the new Foundry portal.»*
A request for `/azure/ai-foundry/concepts/fine-tuning-overview` redirects there.
So the current guidance on choosing between RAG and fine-tuning is published on
the *previous-generation portal's* documentation set. That is not a reason to
distrust it, but it is a reason to date it — this note records what those pages
said on 2026-08-27.

---

## 1. Three techniques, not a competition

> «There are several techniques for adapting a pre-trained language model to suit
> a specific task or domain. These include **prompt engineering, RAG, and
> fine-tuning**. These three techniques are **not mutually exclusive but are
> complementary methods** that in combination can be applicable to a specific use
> case.»

The framing matters: the exam question is rarely "RAG *or* fine-tuning" but
"which one does this symptom call for", and the honest answer is often both.

| Technique | Changes | Costs | Data freshness |
| --- | --- | --- | --- |
| **Prompt engineering** | the request | tokens per call | whatever is in the prompt |
| **RAG** | the request, with retrieved context | retrieval + more input tokens per call | **as fresh as the index** |
| **Fine-tuning** | **the model** | training once + **hosting per hour** + inference | frozen at training time |

The third row is the one that decides architecture: a fine-tuned model is a
build artifact with a shelf life. New facts mean a new training run. An index
means re-running an indexer.

---

## 2. Where each one belongs, in Learn's words

### Prompt engineering — the floor

> «**Prompt engineering is the starting point** for generating desired output
> from generative AI models.»

Not a preliminary to be got through: the stated first move. Block 3 already
measured why — three prompt revisions on the same question, and the first was
fluent and wrong in the direction that costs money.

### RAG

> «RAG is a method that integrates **external data** into a Large Language Model
> prompt to generate relevant responses. This approach is particularly beneficial
> when using a **large corpus of unstructured text based on different topics**. It
> allows for answers to be grounded in the organization's knowledge base.»

Three considerations, quoted as given:

- «RAG helps ground AI output in real-world data and **reduces the likelihood of
  fabrication**.»
- «RAG is helpful when there is a need to answer questions based on **private
  proprietary data**.»
- «RAG is helpful when you might want questions answered that are **recent** (for
  example, before the cutoff date of when the model version was last trained).»

Private, recent, unstructured, broad. Four signals that all point down, not up.

### Fine-tuning

> «Fine-tuning… is an iterative process that adapts an existing large language
> model to a provided training set in order to **improve performance, teach the
> model new skills, or reduce latency**. This approach is used when the model
> needs to **learn and generalize over specific topics, particularly when these
> topics are generally small in scope**.»

⚠️ **"Small in scope" is the opposite of RAG's "large corpus… based on different
topics".** The two sentences were written to be read against each other, and that
contrast is the cleanest discriminator on the page.

> «Good cases for fine-tuning include **steering the model to output content in a
> specific and customized style, tone, or format**, or tasks where **the
> information needed to steer the model is too long or complex to fit into the
> prompt window**.»

Note what is *not* in that list: adding facts. Learn does say fine-tuning
«enhances LLM with after-cutoff-date knowledge and/or domain specific knowledge»,
so the documentation does not claim fine-tuning teaches nothing — but every
*good case* it enumerates is about **form**: style, tone, format, and
instructions too bulky for a prompt. **Form is what fine-tuning buys; facts are
what retrieval buys.** That is the sentence to carry into the exam.

### The two warnings

> «Start by **evaluating the baseline performance** of a standard model against
> their requirements before considering this option.»

> «Having a baseline for performance without fine-tuning is essential for knowing
> whether fine-tuning has improved model performance. **Fine-tuning with bad data
> makes the base model worse, but without a baseline, it's hard to detect
> regressions.**»

Fine-tuning is the only technique here that can make the system *worse* in a way
that is invisible without a prior measurement. It is also the only one that
cannot be rolled back by editing a file. The evaluation set from
`rag-retrieval-evaluation.md` is that baseline — which is a good argument for
building it in this block even though the fine-tune never runs.

### The use case Learn chose to illustrate it

An IT department converting natural language to SQL: responses «not always
reliably grounded in their schema, and the cost is prohibitively high». They
fine-tune `GPT-4o mini` on hundreds of examples and get a model that «performs
better than the base model with **lower costs and latency**».

Read the shape: **narrow task, fixed output format, high call volume**. Volume is
doing quiet work in that example — it is what amortises the hourly host.

---

## 3. When fine-tuning is the cheaper answer

> «Fine-tuning can reduce costs across two dimensions: (1) by using **fewer
> tokens** depending on the task (2) by using a **smaller model** (for example
> GPT-4o mini can potentially be fine-tuned to achieve the same quality of GPT-4o
> on a particular task).»

> «Fine-tuning has **upfront costs for training** the model. And **additional
> hourly costs for hosting** the custom model once it's deployed.»

So the trade is: pay a fixed hourly rent, save on every call. There is a
break-even, and it depends on call volume alone. Below it, fine-tuning is more
expensive than the model it replaces — no matter how good the training data.

⚠️ **Neither dimension is what it first looks like.** Two things the retail price
list says that the guidance does not:

1. **The hosting rate does not vary with model size.** `gpt-4.1-nano-ft`,
   `gpt-4.1-mini-ft` and `gpt-4.1-ft` all host at **1,4937 €/hour** in both
   northeurope and swedencentral. Dropping to a smaller model saves tokens; it
   saves **nothing** on the rent.
2. **Fine-tuned inference is not cheaper per token than the base model.** In
   northeurope, `gpt 4.1 mini Inp glbl` is **0,00040 €/1K** and
   `gpt-4.1-mini-ft input global` is **0,00040 €/1K**; outputs are **0,00140
   €/1K** on both. Identical, to the published precision.

Together those two facts sharpen Learn's cost claim considerably. Fine-tuning
does not buy a discount rate. It reduces cost only by letting you send **fewer
tokens** — a shorter prompt, because the instructions now live in the weights —
or by letting a **smaller model** do a job that previously needed a larger one.
Both savings are real; neither arrives automatically, and both are levied against
a fixed 35,85 €/day.

### This project's break-even

At 1,4937 €/hour the host costs **35,85 €/day** whether or not a single request
arrives. Against `gpt-4.1-mini` on GlobalStandard at **0,00140 €/1K output**
(northeurope, the deployment type block 3 used), a day of hosting buys roughly
**25 million output tokens** on the base model.

This repository's entire measured history is **~1.300 tokens to build block 3**
and **≈0,81 € of Azure spend across all of August**. The break-even is four
orders of magnitude away. Fine-tuning is not marginal here; it is not in the same
universe as this workload, and no amount of care in running it would change that.

**Decision: block 5 does not fine-tune.** Same reasoning, same shape and the same
verdict as provisioned throughput in block 3 — 15 units minimum at 13,16 €/hour,
stopped only by deleting it. The exam asks which technique fits a scenario, not
whether the author can afford to rent a GPU.

---

## 4. What is being given up, and what is not

Not exercising fine-tuning costs access to these, which stay theory:

| Technique | What it is | Best for | Supported models |
| --- | --- | --- | --- |
| **SFT** — Supervised Fine-Tuning | trains on input/output pairs | «**Start here for most projects.** SFT addresses the broadest number of fine-tuning scenarios» | GPT-4o, 4o-mini, 4.1, 4.1-mini, 4.1-nano; Llama 2 / 3.1; Phi 4; Mistral family |
| **DPO** — Direct Preference Optimization | learns from preferred vs non-preferred outputs, **no separate reward model** | response quality, safety, alignment, style and cultural preference | GPT-4o, 4.1, 4.1-mini, 4.1-nano |
| **RFT** — Reinforcement Fine-Tuning | reinforcement learning against reward signals | «objective domains like mathematics, chemistry, and physics where there are clear right and wrong answers **and the model already shows some competency**» | **o4-mini only** |

⚠️ Three exam-shaped details in that table: **RFT supports exactly one model**;
**DPO is not available for 4o-mini**; and RFT «works best when lucky guessing is
difficult and expert evaluators would consistently agree on an unambiguous,
correct answer» — a scope test, not a capability test.

Two more, both cheap to remember and easy to get wrong:

- **Serverless vs managed compute.** Serverless is «consumption-based pricing
  starting at $1.70 per million input tokens», needs **no GPU quota**, and is the
  **only** path to OpenAI models. Managed compute offers more models and more
  control but «requires you to provide your own VMs for training and hosting» and
  «doesn't include OpenAI models». For most customers, serverless.
- **Data volume.** «Start with **50-100 high-quality examples** for initial
  testing, scaling to **500+** for production models.» Small — which is the point
  of "small in scope" in § 2, and another reminder that fine-tuning is not how a
  corpus gets into a model.

And the permission fact this repository already has in writing
(`foundry-rbac-and-authentication.md` § 5): fine-tuning needs **both planes**, so
the only single built-in role that covers it is **Foundry Owner** — or **Foundry
User** (data) plus **Foundry Account Owner** (control). Subscription `Owner` does
not, because its data-actions column is ✘.

**What is not given up:** the decision itself. Every question this domain asks
about fine-tuning is answerable from §§ 2–4, and none of it requires having paid
the rent.

---

## 5. What this note would cost to verify

| Claim | Cost | Verdict |
| --- | --- | --- |
| Hosting rate 1,4937 €/h, flat across model sizes | **0,00 €** — retail price API, no auth | ✅ already done, § 3 |
| Training rate per 1K tokens | **0,00 €** — same query | ✅ already done |
| A training job runs and produces a model | training tokens only, ~5,80 € per million | possible, and pointless without the next row |
| **A fine-tuned model answers anything** | **1,4937 €/h from deployment to deletion** | ❌ excluded |
| SFT/DPO/RFT model support matrix | **0,00 €** — documented | ✅ read |
| Fine-tuning needs both RBAC planes | **0,00 €** — documented, and half-measured in block 3 | ✅ |

The fourth row is the whole exclusion, and it is worth being precise about why:
**training is affordable and hosting is not**. A training run on a small dataset
is a few euros; the deployment that makes it usable is 35,85 €/day until someone
deletes it, on a subscription whose spending limit is Off. Block 3 wrote the same
sentence about PTU and it held.

If it were ever run, the deletion command belongs next to the creation command in
the same paragraph — see `rag-cost-model.md` § 5.

---

## Sources

- [Getting started with customizing a large language model (LLM) (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/customizing-llms) — read 2026-08-27; §§ 1, 2, 3
- [Fine-tune models with Microsoft Foundry (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/concepts/fine-tuning-overview) — read 2026-08-27; § 4
- Azure Retail Prices API, `contains(meterName,'hosting')`, northeurope + swedencentral, EUR — read 2026-08-27; § 3 hosting and training rates
- `foundry-cost-model.md` — provisioned throughput, the same decision taken in block 3
- `foundry-rbac-and-authentication.md` § 5 — fine-tuning needs both permission planes
- `rag-retrieval-evaluation.md` — the baseline Learn says to establish before fine-tuning
- `rag-cost-model.md` § 4 — the euros behind § 3
