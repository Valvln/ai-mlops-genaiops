# Foundry block 3 — a model, a versioned prompt, and a call I can find later

Feature 006. The smallest Azure AI Foundry deployment that exercises AI-300
Domain 3: one token-billed model deployment, a prompt that lives in git rather
than in a portal, and a call whose record I can retrieve after the terminal
that made it is gone.

It lives in its own resource group in `swedencentral`, deployed by hand from
[`infra/foundry.bicep`](../../infra/foundry.bicep) — not by CI, and nothing to
do with `main.bicep`'s `northeurope` backbone. Either can be destroyed without
touching the other.

## What is here

| File | Role |
| --- | --- |
| `prompts/hello-domain3.prompty` | The prompt, with the deployment name and sampling parameters in its frontmatter |
| `call_model.py` | Loads the prompt file, sends one call, emits a span carrying the prompt's git revision |
| `query_trace.py` | Reads a past call back out of Log Analytics, as a separate process |
| `pyproject.toml` | The pinned local environment (`uv sync`) |

The infrastructure is one file up, in `infra/foundry.bicep`. Setup and the
full run-through are in
[`specs/006-foundry-genaiops/quickstart.md`](../../specs/006-foundry-genaiops/quickstart.md).

## The question this block existed to answer

**Can I prove which prompt produced a given answer, after the fact?**

**Yes, but only because the span is flushed explicitly.** Everything else was
straightforward; this was not, and it nearly passed while being broken.

The first version of `call_model.py` ended when its span closed and let the
OpenTelemetry batch processor ship whatever it had at interpreter exit. One
call had already been retrieved successfully, so tracing looked proven. Then a
second call went missing: three hours later the workspace still held exactly
one record, so this was a loss and not ingestion lag. A span queued in a batch
processor is not a span that was exported, and a short-lived CLI process is
exactly where that gap opens — the process is gone long before the next
scheduled export.

What exposed it was a success criterion that demanded **two** records instead
of one. A single retrieval would have shipped a mechanism that works about
half the time.

## What Owner does not buy

Three permission surfaces, three different answers, and I got two of them
wrong before the service corrected me:

| Operation | Guarded by | Owner enough? |
| --- | --- | --- |
| Log Analytics query | control-plane action | **yes** |
| Chat completions | data action | **no** — `401`, fixed with `Cognitive Services OpenAI User` |
| Reading a Foundry connection | data action | **no** — not granted, see below |

The plan predicted I would need `Log Analytics Reader` and would not need
anything for inference. Both backwards. Which plane guards an API has to be
read off the refusal, not inferred from how strong the role sounds.

**Correction, 2026-08-26 — the mechanism above is right, the role name is not.**
Reading the current documentation for the Domain 3 mock exam turned up two
sentences that supersede the middle row. Learn now prescribes **`Foundry User`**
(recently renamed from `Azure AI User`) on the Foundry account scope as the role
for calling a deployment at inference time, and says in as many words: *"Don't
assign built-in roles that start with Cognitive Services. These roles are
designed for accessing AI Services resources directly and don't apply to Foundry
scenarios."* `Cognitive Services OpenAI User` did fix the `401` here — that is an
observation, not a mistake — but it is the older, wider grant, and it is not the
answer this exam wants. The full role table is in
`docs/exam-notes/foundry-rbac-and-authentication.md` § 3.

The third one I deliberately left refused. The tidy way to configure tracing is
to let the app discover its own telemetry target through the project's
Application Insights connection, but that needs
`Microsoft.CognitiveServices/accounts/AIServices/connections/read`. The only
built-in role carrying it grants the entire Cognitive Services data plane for
one lookup, and a one-action custom role would be an authorization-provider
object that survives `az group delete` — residue in a resource group whose
whole point is that deleting it leaves nothing. So the connection string comes
from the App Insights resource, and the two connections stay what they are:
the wiring the portal reads.

## Prompt iteration, as a diff

Three revisions, same question each time. This is the part that would be
invisible if the prompt lived in the portal.

| Revision | What the model said about Standard |
| --- | --- |
| `24dab02` | "automatically scales compute resources based on demand" |
| `d65f3d8` | "bills per token processed and incurs no charges when idle" |
| `38d92d5` | …and "can be scaled down or turned off to stop billing" |

Revision 1 was fluent and wrong in the direction that costs money — it
described elastic compute instead of per-token billing. Revision 2 added a
rule naming the billing unit. Revision 3 added one about reversibility.

## Observed values

| | Value |
| --- | --- |
| Region | `swedencentral` |
| Model | `gpt-4.1-mini`, version `2025-04-14`, `GlobalStandard`, capacity 1 |
| Quota meter | `OpenAI.GlobalStandard.gpt4.1-mini`, limit 200 |
| Resources created | 4 listed + 1 deployment, 2 connections, 1 role assignment |
| Ingestion lag, observed | 2–3 minutes |
| Tokens spent building this | ~1,300 |
| Cost at rest | **Expected €0.00/day, not yet measured.** The Retail Prices API publishes no per-hour meter for any of these four resource types in `swedencentral` — but that is a price list, not an observation, and SC-006 exists to take the observation. Pending T027 |

`gpt-4.1-mini` is not the model the cost model recommended. `gpt-5-nano` was
cheaper and undeployable: quota 0 in this subscription. `gpt-4o-mini` was
deprecated. The catalog says a SKU exists in a region; only
`az cognitiveservices usage list` says this subscription can use it — and it
spells the model `gpt4.1-mini` for standard SKUs and `gpt-4.1-mini` for batch
ones, so a query filtered on the real name reports a healthy quota for a SKU
nobody is deploying.

## Teardown

```bash
az group delete --name rg-ai300-foundry --yes
```

One command, nothing left behind: no soft-deleted vault holding a globally
unique name for 90 days, no role definition outliving its scope. The role
assignment is scoped to the account and dies with it.
