# The Foundry resource model — what an account, a project and a hub each are

**Status: partially built.** Feature 006 created a Foundry account and a Foundry
project by hand from `infra/foundry.bicep`, in `swedencentral`. **No hub has ever
existed in this subscription**, and no standalone Azure OpenAI resource either —
so half of this note is the shape of things this repository deliberately did not
create.

Every behavioural claim below comes from the Microsoft Learn pages listed under
*Sources*, read on **2026-08-21**. Prices are not restated here: they are in
`foundry-cost-model.md`, which priced this decision before the first deployment.

---

## 1. Four resource types, and only two of them are choices

| Resource type | What it is | When you need it |
| --- | --- | --- |
| **Foundry** | «An Azure resource that scopes design, deployment, governance, and runtime access for generative AI applications and agents, including agent service, Microsoft- and partner-provided models, evaluations, Foundry Tools, and Azure OpenAI–compatible APIs.» **The default resource type** for projects built in the Foundry portal | the default; assume this unless something forces otherwise |
| **Azure OpenAI** | «A specialized resource type that provides access to **OpenAI models and APIs only**» | only if your IT security team hasn't enabled the superset of Foundry capabilities in your environment |
| **Azure AI Hub** | The previous-generation container. Most of its capabilities moved under the Foundry resource type starting **June 2025** | «Select use cases, **including open source model deployments**, currently still require a hub resource» |
| **Azure AI Search** | A resource you *connect*, not an alternative container: indexes and retrieves data for grounding | RAG and semantic search over your own data |

The two sentences worth memorising verbatim, because they are the two most
likely stems of an exam question:

> «For most use cases, use the Foundry resource, which offers **backward
> compatibility with all Azure OpenAI APIs**.»

> «New features primarily land on Foundry resource type.»

### 1a. The upgrade path from Azure OpenAI

A team with a live Azure OpenAI resource does **not** have to repoint its
applications. Learn documents an upgrade option from Azure OpenAI to Foundry that
gives access to all Foundry capabilities and models **«while keeping your
existing Azure OpenAI API endpoint, state of work, and security
configurations»**.

The wrong answers this fact exists to kill: "create a new resource and repoint
everything", and "create a hub and attach the Azure OpenAI resource as a
connection". Neither is the documented path.

### 1b. The hub is not a variant of the Foundry resource

A hub carries dependencies — storage, Key Vault, container registry, Application
Insights, optionally AI Search — and two of them **cannot be detached once
attached**. That dependency table, with rates, is `foundry-cost-model.md` § 1b
and is not repeated here. It is the reason feature 006 chose the lean path.

Hub-based projects are now reachable through the **Foundry (classic)** portal;
new investment is on Foundry projects in the new portal.

---

## 2. Account, project, agent — the three scopes

A Foundry project is a **child resource of the account**, not a peer. The RBAC
documentation makes the hierarchy explicit, and the agent-scope URI shows the ARM
path end to end:

```
/subscriptions/<sub>/resourceGroups/<rg>
  /providers/Microsoft.CognitiveServices/accounts/<account>
    /projects/<project>
      /agents/<agent>
```

| Scope | Learn's definition | Role assignments there |
| --- | --- | --- |
| **Foundry resource** | «The top-level scope that defines the administrative, security, and monitoring boundary for a Microsoft Foundry environment» | everything |
| **Foundry project** | «A sub-scope within a Foundry resource used to organize work and enforce access control for Foundry APIs, tools, and developer workflows» | everything |
| **Agent** | «A narrower scope within a Foundry project that applies to an individual agent» | **evaluated only for agent endpoint access** |

The agent scope carries a trap worth the exam question it will become:

> «The system currently assesses agent-scope role assignments **only for agent
> endpoint access**. Assigning a role at the scope of an individual agent affects
> whether the assignee can interact with that agent's endpoints, but it **doesn't
> grant broader control-plane or management permissions**.»

Any role assignable at project scope is also assignable at agent scope. The
mechanics are identical; only the *evaluation* is narrowed. So an agent-scope
`Foundry Owner` does not manage that agent — it talks to it.

---

## 3. Limits that decide an architecture

Four numbers, and three of them live on adjacent rows of the same table, which is
exactly how they get confused.

| Limit | Value |
| --- | --- |
| Foundry resources per region per Azure subscription | **100** |
| Projects per Foundry resource | **250** |
| **Model deployments per Foundry resource** | **32** |
| Fine-tuned model deployments (Azure OpenAI limits) | **10** |
| Azure OpenAI resources per Azure subscription | 30 |
| Custom headers per API request | **10** — more returns HTTP **431** |

The header limit is not trivia: «Future API versions won't pass through custom
headers. Don't depend on custom headers in future system architectures.» Any
design that carries tenant IDs or correlation data in custom headers is building
on something Microsoft has announced it will remove.

---

## 4. What changed under the rename, and why the exam cares

Foundry consolidated several products, and the vocabulary moved with it. The
exam is written against the current names; the internet is full of the old ones.

| Dimension | Previous | Current |
| --- | --- | --- |
| Brand | Azure AI Studio / Azure AI Foundry | **Microsoft Foundry** |
| Brand | Azure AI Services | **Foundry Tools** |
| Portal | Foundry (classic) | Foundry |
| Resource model | Hub + Azure OpenAI + Azure AI Services | **Foundry resource** (single, with projects) |
| Agent API | Assistants API (Agents v0.5/v1) | **Responses API** (Agents v2) |
| API versioning | monthly `api-version` params | **v1 stable routes** (`/openai/v1/`) |
| SDKs and endpoints | multiple packages against 5+ endpoints | unified project client (`azure-ai-projects` 2.x) + `OpenAI()` against **one project endpoint** |
| Terminology | Threads, Messages, Runs, Assistants | **Conversations, Items, Responses, Agent Versions** |

The RBAC roles were renamed too, and that has a sharper consequence — see
`foundry-rbac-and-authentication.md` § 3.

**The Assistants API is deprecated and retires 26 August 2026.** Anything built
on Threads/Runs is on a clock.

---

## 5. What this repository did, and where it now diverges from Learn

| Decision in feature 006 | Still correct? |
| --- | --- |
| Foundry account + Foundry project, no hub | ✅ — and § 1b is why |
| `swedencentral` rather than `northeurope` | ✅ — a quota decision, see `foundry-quota-and-rate-limits.md` § 5 |
| `customSubDomainName` set | ✅ — required for Entra token auth |
| `disableLocalAuth: true` | ✅ — see `foundry-rbac-and-authentication.md` § 4 |
| ⚠️ `Cognitive Services OpenAI User` for inference | **superseded** — Learn now says not to use `Cognitive Services*` roles for Foundry scenarios. See `foundry-rbac-and-authentication.md` § 3 |

---

## 6. What this note would cost to verify

**Nothing that isn't already spent.** Every claim here is a property of the
resource model, readable from `az cognitiveservices account show`, the ARM path
of an existing resource, or a limits table. The one item with a real price is the
hub, and the whole point of `foundry-cost-model.md` § 1b was to price it *without*
creating one — a hub's registry bills 4.4 €/month whether or not anything uses
it, and cannot be detached afterwards.

The honest gap this leaves: **this repository has never seen a hub-based project,
so anything about prompt flow, open-source model hosting or hub-scoped
connections is read, not observed.** It is declared theory in the same sense as
`network-isolation.md`, and for the same reason.

---

## Sources

- [Choose an Azure resource type for Foundry (classic)](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/resource-types) — read 2026-08-21
- [What is Microsoft Foundry?](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry) — read 2026-08-21; the evolution table in § 4
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry) — read 2026-08-21; the scope definitions and agent-scope URI in § 2
- [Microsoft Foundry Models quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/quotas-limits) — read 2026-08-21; the resource limits in § 3
- [Azure OpenAI quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/quotas-limits) — read 2026-08-21; the fine-tuned deployment and resource-count limits
- `foundry-cost-model.md` § 1, § 2 — the hub dependency table and every euro figure
- `infra/foundry.bicep`, `genaiops/foundry-block3/README.md` — the decisions in § 5
