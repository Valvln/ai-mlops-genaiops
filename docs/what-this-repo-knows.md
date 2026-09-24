# What this repository knows that Learn does not say

An index, not a note. Everything here is recorded in full somewhere else; this
page answers one question — **where is the thing we measured, and does it agree
with the source?** — so that revision does not mean rereading eighteen notes.

Built 2026-09-22 from `docs/exam-notes/` (18 sourced notes), the nine findings
of feature 007 (block 4) and the ten of feature 008 (block 5).

## How to read the verdict column

| Verdict | Meaning |
| --- | --- |
| **confirms** | measurement matched the source; the note carries the verification |
| **extends** | source is silent or incomplete; we measured the number it does not publish |
| **contradicts** | source and behaviour disagree, and the entry says which is wrong |
| **corrects us** | we were wrong, the source was right; kept because the wrong turn is instructive |

The last two are the ones to reread before an exam. They are marked ⚠️.

---

## Domain 3 — Generative AI solutions

| # | What we know | Where | Verdict |
| --- | --- | --- | --- |
| 1 | **The SDK samples your spans by default, and the resource's `samplingPercentage` does not show it.** `RateLimitedSampler{5.0}` since distro 1.8.6; its percentage starts at 0% and needs ~0.5 s of process life to reach 100%, so a short-lived CLI loses most spans. Measured offline: 1 of 12 spans kept, 12 of 12 with `sampling_ratio=1.0`. Verified against Azure on 2026-09-24: 3 of 12 arrived in Log Analytics with the default sampler, 12 of 12 with the fix. | [genai-tracing § 7b](exam-notes/genai-tracing.md), [007 F6](../specs/007-genai-eval-observability/findings.md) | ⚠️ **contradicts** — and cost two days on a wrong "service-side" conclusion |
| 2 | **A span queued in a batch processor is not a span that was exported.** A short-lived process exits before the scheduled export. Learn's own console sample quietly uses `SimpleSpanProcessor`. | [genai-tracing § 7](exam-notes/genai-tracing.md) | **extends** — the trap is not on any page |
| 3 | **`force_flush() == True`, `HTTP 200` and `Items accepted: 8` are three acknowledgements and none means "queryable".** A dropped span was never queued, so the flush is honest and useless. | [genai-tracing § 7b](exam-notes/genai-tracing.md), [007 F6](../specs/007-genai-eval-observability/findings.md) | **extends** |
| 4 | **Metrics are never sampled; spans are.** `AppMetrics` landing while `AppDependencies` stays empty proves the pipe is open and says nothing about your traces. | [genai-tracing § 7b](exam-notes/genai-tracing.md) | **confirms** — and it is the fastest diagnostic in the repo |
| 5 | **`AzureOpenAIModelConfiguration(credential=...)` is documented and unusable.** Declared `NotRequired[Any]`; the SDK validates TypedDicts with `isinstance()`, which rejects `Any`. The error then blames every Azure key as "unknown". Still broken in 1.18.3. Pass the credential to the evaluator instead. | [007 F4](../specs/007-genai-eval-observability/findings.md) | ⚠️ **contradicts** — defect in the SDK, not in us |
| 6 | **`capacity: 1` means one request per minute.** On a token-billed SKU capacity is a throttle, not a reservation: raising it to 10 changes no price. On a provisioned SKU the same number is a billing floor. | [007 F3](../specs/007-genai-eval-observability/findings.md), [foundry-cost-model § 6](exam-notes/foundry-cost-model.md) | **confirms** |
| 7 | **Every child of a Cognitive Services account contends for one account-level lock.** Pairwise `dependsOn` moves the race; the template must chain all four children. Feature 006 passed on luck. | [007 F1](../specs/007-genai-eval-observability/findings.md) | **confirms** — parallel-by-default is documented |
| 8 | **Two connections on one account cannot share a name**, because a project is projected as an AML workspace sharing the account's connection namespace. The error blames an unauthorised cross-workspace update. | [007 F2](../specs/007-genai-eval-observability/findings.md) | **extends** — source silent |
| 9 | **`disableLocalAuth` does not remove the keys, only their acceptance.** `az ... keys list` still returns them. | [008 F4](../specs/008-rag-retrieval-quality/findings.md) | ⚠️ **contradicts** the intuitive reading |
| 10 | **Reading a project connection is a data action**, so the App Insights connection string is taken from the component instead. The only built-in role carrying it grants the whole data plane for one lookup. | [genai-tracing § 2](exam-notes/genai-tracing.md), [foundry-rbac § 1](exam-notes/foundry-rbac-and-authentication.md) | **confirms** |
| 11 | **`Cognitive Services OpenAI User` works and is not what Learn prescribes** — `Foundry User` on the account scope is, with Cognitive Services roles explicitly discouraged. The measurement was sound; the conclusion was incomplete. | [foundry-rbac](exam-notes/foundry-rbac-and-authentication.md), `genaiops/foundry-block3/README.md` | ⚠️ **corrects us** — this is why constitution § 1.1.0 exists |
| 12 | **Foundry versions an agent on every create or update, portal or SDK alike.** Git versions the *text*, with a diff and an author. Different artefacts, different questions. | [prompt-and-agent-versioning §§ 2–3](exam-notes/prompt-and-agent-versioning.md) | **confirms** — read, not observed |
| 13 | **Prompt flow retires 2027-04-20 and is hub-only.** Container images already receive no security updates. The variant *pattern* outlives the product. | [prompt-and-agent-versioning § 6](exam-notes/prompt-and-agent-versioning.md) | **confirms** |
| 14 | **Message content is opt-in**: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. "We see latency and tokens but not prompts" is one environment variable, not a bug or a permission. | [genai-tracing § 3](exam-notes/genai-tracing.md) | **confirms** |

## Domain 4 — Quality, evaluation, observability

| # | What we know | Where | Verdict |
| --- | --- | --- | --- |
| 15 | **The default groundedness threshold of 3 passes a confident fabrication.** A 1–5 score averages inventions against correct parts: the judge named all three fabrications and still returned `pass` at 4.0. At threshold 5 the same score fails. | [007 F5](../specs/007-genai-eval-observability/findings.md) | **extends** — the default is documented, its adequacy is not |
| 16 | **An LLM-as-judge metric has two independently wrong things — the score and the threshold — and only the first is the model's.** | [007 F5](../specs/007-genai-eval-observability/findings.md) | **extends** |
| 17 | **A trace store is a dependency, not a given.** Anything derived from it inherits its losses — and a cost counter derived from it fails *toward under-reporting*, the flattering direction. Measured: 3 counted against ~13 real calls. | [007 F6](../specs/007-genai-eval-observability/findings.md) | **extends** |
| 18 | **The evaluator's metrics are not where the return value appears to put them.** | [008 F5](../specs/008-rag-retrieval-quality/findings.md) | ⚠️ **contradicts** |
| 19 | **A record is verified when a separate process reads it back.** Why `evaluate_call.py` and `query_evaluations.py` are two programs. | [007 F6](../specs/007-genai-eval-observability/findings.md), `qa-observability/foundry-block4/README.md` | **extends** |
| 20 | **One of two control questions was not a control.** A control that does not control is worse than none. | [008 F6](../specs/008-rag-retrieval-quality/findings.md) | ⚠️ **corrects us** — defect in our own spec |
| 37 | **A failed evaluation is still a record.** The span is written before the judge call, so a judge call that fails is exported with no score and no result. The reader prints it as an evaluation with `score: None`, and the invocation counter counts it. Measured: 10 counted for 8 model invocations. | [007 F9](../specs/007-genai-eval-observability/findings.md) | **extends** |

## Domain 5 — RAG and retrieval

| # | What we know | Where | Verdict |
| --- | --- | --- | --- |
| 21 | **The documented vector-index size formula underestimates by 3×.** | [008 F2](../specs/008-rag-retrieval-quality/findings.md) | ⚠️ **contradicts** the published formula |
| 22 | **The Free tier publishes no vector quota, and neither does the service.** | [008 F1](../specs/008-rag-retrieval-quality/findings.md), [rag-vector-store](exam-notes/rag-vector-store-and-indexing.md) | **extends** |
| 23 | **Index statistics report zero after a successful push.** Statistics lag; the push is not wrong. | [008 F3](../specs/008-rag-retrieval-quality/findings.md) | ⚠️ **contradicts** the obvious reading |
| 24 | **RRF fusion ranked worse than its own vector leg.** Hybrid is not automatically better; measure it. | [008 F7](../specs/008-rag-retrieval-quality/findings.md), [rag-hybrid-search](exam-notes/rag-hybrid-search-and-ranking.md) | ⚠️ **contradicts** the usual advice |
| 25 | **Three score ranges, not one.** RRF scores, vector similarity and the L2 reranker are not comparable to each other. | [rag-hybrid-search](exam-notes/rag-hybrid-search-and-ranking.md) | **confirms** |
| 26 | **Retrieval metrics that need labels need labels.** Process evaluation is what you can do without ground truth. | [rag-retrieval-evaluation](exam-notes/rag-retrieval-evaluation.md) | **confirms** |
| 27 | **The idle-day cost result inverted what the success criterion predicted**, and the real result is the stronger one. | [008 F9](../specs/008-rag-retrieval-quality/findings.md), [rag-cost-model](exam-notes/rag-cost-model.md) | ⚠️ **corrects us** |

## Domains 1–2 — Infrastructure, deployment, classical ML

| # | What we know | Where | Verdict |
| --- | --- | --- | --- |
| 28 | **A Log Analytics workspace is silently restored by the next same-name deploy.** Recovery *is* re-creating it with the same subscription, group, name and region — which is exactly what a Bicep redeploy does. Reported as a successful create, old data included. | [DEPLOY § 6.1b](../infra/DEPLOY.md), [007 F8](../specs/007-genai-eval-observability/findings.md) | **confirms** — documented behaviour, undocumented *by us* until now |
| 29 | **Purge the workspace BEFORE deleting the resource group.** The purge is addressed through the group; afterwards there is no route to it, and `--force true` **exits 0 with no output** while doing nothing. 30-day residue, no bill. First executed in this order on 2026-09-24, and it worked: the workspace was absent from `list-deleted-workspaces` afterwards. | [008 F10](../specs/008-rag-retrieval-quality/findings.md), [DEPLOY § 6.1b](../infra/DEPLOY.md), [007 F6](../specs/007-genai-eval-observability/findings.md) | ⚠️ **contradicts** block 4's remedy, which did not generalise |
| 30 | **Key Vault purge protection is irreversible and holds the name 90 days.** `--enable-purge-protection false` returns `BadRequest`. Names derive from `uniqueString(resourceGroup().id)`, so reusing a group name collides. | [DEPLOY § 6.1](../infra/DEPLOY.md) | **confirms** |
| 31 | **The custom CI role definition does not survive a teardown**, contradicting what this runbook used to assert. Confirmed twice, the second time by `GET` on the definition id. | [DEPLOY § 6.2](../infra/DEPLOY.md) | ⚠️ **corrects us** |
| 32 | **`az bicep build` proves compilation, not deployability.** Region eligibility, name lengths and ordering races are invisible to it. Only `what-if` against the live subscription sees them. | [DEPLOY](../infra/DEPLOY.md), `CLAUDE.md` | **extends** |
| 33 | **A failing `az` command may never have reached Azure.** `No subscriptions found` is client-side, resolved from a local cache, and is not an authorization refusal. | `CLAUDE.md`, [DEPLOY](../infra/DEPLOY.md) | **extends** |
| 34 | **The CI role permits a fixed set of operations, and a new resource type fails the next deploy with `AuthorizationFailed`.** Designed behaviour: add the named operation with the failing run as provenance, never a built-in role. | [DEPLOY § 5](../infra/DEPLOY.md), `infra/ci-identity.bicep` | **confirms** |
| 35 | **`westeurope` rejects this subscription** with `RequestDisallowedByAzure`; it is not accepting new customers. Use `northeurope`. | `CLAUDE.md`, [DEPLOY](../infra/DEPLOY.md) | **extends** |
| 36 | **Node-hours, not job count, set the bill** for a sweep — the thing a Domain 2 simulation got wrong. | [hyperparameter-sweep](exam-notes/hyperparameter-sweep.md), [compute-cost-model](exam-notes/compute-cost-model.md) | ⚠️ **corrects us** |

---

## The pattern worth naming

Nine of the entries above are ⚠️, and they are not nine unrelated surprises.
Most are one shape: **a check that passes while its objective is missed.**

- `force_flush()` returns true on spans that were never queued (#1, #3)
- `--force true` exits 0 on a purge that did nothing (#29)
- a groundedness gate returns `pass` on a named fabrication (#15)
- `az bicep build` goes green on a template that cannot deploy (#32)
- a redeploy reports "created" on a workspace it recovered (#28)
- an invocation counter reads 3 for 13 calls, in the flattering direction (#17)
- a control question that controls nothing (#20)

The repository's standing answer is to make the check's objective, not its exit
code, the success criterion — which is why feature 006 demanded *two* retrieved
records rather than one, and why that is the one time the design of the check
caught the bug.

The second pattern, smaller but expensive: **a pinned range is not a pinned
behaviour** (#1). `>=1.6,<2.0` accepted a documented breaking change to a
default, with no commit here to mark it.

## Where each thing lives

| Kind | Path | Contract |
| --- | --- | --- |
| Sourced notes | `docs/exam-notes/` | drawn from official docs, each listing sources and read date |
| Findings | `specs/<NNN>-<slug>/findings.md` | measured, each carrying the command and output |
| Deployment runbook | `infra/DEPLOY.md` | written before the first deploy, revised with observed values |
| This index | `docs/what-this-repo-knows.md` | pointers only; no fact originates here |

Adding an entry: record it in its own place first, then add one row here. If a
row and its source disagree, the source wins and the row is wrong.
