# RBAC and authentication for Foundry — the same split, on a fourth service

**Status: the control-plane / data-plane split was learned here the hard way,
and the role names this repository used are now the wrong ones.** Feature 006
found that Owner on the Foundry account queried Log Analytics happily and got
`401` on chat completions. That lesson is intact and is documented in
`genaiops/foundry-block3/README.md`. The **role it was fixed with** —
`Cognitive Services OpenAI User` — is what Learn now tells you not to use for
Foundry scenarios. § 3 is that correction.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-08-21**.

---

## 1. Control plane and data plane

> «Foundry divides operations into **control plane** (resource management) and
> **data plane** (runtime usage), each with its own authentication and
> role-based access control surface.»

| Plane | Scope in Foundry | Typical operations | Tools | Authorization surface |
| --- | --- | --- | --- | --- |
| **Control** | resource, projects, networking, encryption, connections | create or delete resources, assign roles, rotate keys, set up Private Link | portal, CLI, ARM, Bicep, Terraform | Azure RBAC **`actions`** |
| **Data** | model inference, agent interactions, evaluation jobs, content safety | chat completions, embeddings, start fine-tune jobs, send agent messages | SDKs, REST, portal playground | Azure RBAC **`dataActions`** |

The one-line rule, straight from the page: **RBAC `actions` are control plane;
RBAC `dataActions` are data plane.**

The enumerated lists matter, because two of the entries are counter-intuitive:

**Control plane actions** — Foundry resource creation, Foundry project creation,
Account Capability Host creation, Project Capability Host creation, **model
deployment**, account and project connection creation.

**Data plane actions** — building agents, running an evaluation, **tracing and
monitoring**, fine-tuning.

So *creating* a deployment is control plane and *calling* it is data plane;
*fine-tuning* is data plane but *deploying the fine-tuned result* is control
plane. That asymmetry is § 5.

This is the fourth service on which this repository has met the same split:
Key Vault (Domain 1 simulation), Azure ML online endpoints
(`online-endpoints.md` § 3), Azure ML managed networks
(`network-isolation.md` § 3), and now Foundry. **Which plane guards an API has to
be read off the refusal, not inferred from how strong the role sounds.**

---

## 2. Two authentication methods

### Microsoft Entra ID

- OAuth 2.0 bearer tokens scoped to **`https://ai.azure.com/.default`**
- Requires a **custom subdomain** on the Foundry resource — this is a hard
  prerequisite, and its absence produces a specific error (§ 7)
- Gives conditional access, MFA, managed identities, per-principal auditing,
  controllable token lifetimes

### API keys

> «API keys are static secrets scoped to a Foundry resource… **the key grants
> full access without role restrictions**.»

> «Can't express user identity, is difficult to scope granularly, and is harder
> to audit. Generally not accepted by enterprise production workloads and **not
> recommended by Microsoft**.»

A key is not a weaker role. It is the *absence* of roles: a caller with a key
bypasses RBAC entirely. That is why `infra/foundry.bicep` sets
`disableLocalAuth: true` — identity doing the work that network isolation would
otherwise do, as `network-isolation.md` § 4 puts it.

### What keys cannot do at all

The feature matrix is the exam-shaped part, because the answer is not "keys work
everywhere, just less safely":

| Capability | API key | Entra ID |
| --- | --- | --- |
| Basic model inference (chat, embeddings) | ✔ | ✔ |
| Fine-tuning operations | ✔ | ✔ |
| Content safety analyze calls | ✔ | ✔ |
| Batch inferencing, portal playground | ✔ | ✔ |
| **Agents service** | ✘ | ✔ |
| **Evaluations** | ✘ | ✔ |
| **Least privilege with built-in or custom roles** | ✘ | ✔ |
| **Managed identity (system or user-assigned)** | ✘ | ✔ |
| **Per-request user attribution** | ✘ | ✔ |

Revocation differs too: a key is *rotated*; an Entra principal has its role
removed or is disabled, subject to token lifetime.

---

## 3. ⚠️ The roles were renamed, and two families are traps

### The rename

| Current name | Previous name | Role definition ID |
| --- | --- | --- |
| **Foundry User** | Azure AI User | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |
| **Foundry Owner** | Azure AI Owner | `c883944f-8b7b-4483-af10-35834be79c4a` |
| **Foundry Account Owner** | Azure AI Account Owner | `e47c6f54-e4a2-4754-9501-8e0985b135e1` |
| **Foundry Project Manager** | Azure AI Project Manager | `eadc314b-1a2d-4efa-be10-5d325db5065e` |

Learn's own advice for scripts and templates: **use the GUID, not the name**, to
survive the rollout. The role IDs and permissions are unchanged by the rename.

### The two families not to use

> «**Don't assign built-in roles that start with Cognitive Services.** These
> roles are designed for accessing AI Services resources directly and don't apply
> to Foundry scenarios. Similarly, **don't use the Azure AI Developer role** for
> Foundry work. Despite the name, this role is scoped to Azure Machine Learning
> workspaces and Foundry hubs, **not** to Foundry projects or Foundry hosted
> agents. For Foundry project access, use **Foundry User** or **Foundry Owner**.»

`Azure AI Developer` is the sharper trap of the two: it is the role whose name
most sounds like the answer, and it points at the previous-generation container.

**What this means for this repository.** Feature 006 fixed its `401` with
`Cognitive Services OpenAI User` and it worked — that is an observation, not an
error. But the role Learn prescribes for calling a deployment is:

> «To call a deployment at inference time, assign the **Foundry User** role on
> the **Foundry account scope** (or use the account API key).»

`genaiops/foundry-block3/README.md` documents the older path and should say so
when it is next touched.

---

## 4. The built-in roles

| Role | What it grants |
| --- | --- |
| **Foundry Agent Consumer** | interact with agent endpoints in a project. **Least-privilege role for principals that only consume agents** |
| **Foundry User** | reader access to project and resource, plus **data actions** for the project. Least-privilege role for developers building and testing agents |
| **Foundry Project Manager** | management actions on projects, build and develop, publish agents, and conditionally assign **Foundry User** to others |
| **Foundry Account Owner** | full access to manage projects and resources; conditionally assign Foundry User, ACR and monitoring roles. **No data actions** |
| **Foundry Owner** | full management **and** build/develop. «Highly privileged self-serve role» |

### The permission matrix, which is where the exam questions come from

| Role | Create projects | Create accounts | **Data actions** | Assign roles | Read | Manage models | Publish agents | Agent endpoints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Foundry Agent Consumer | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ |
| Foundry User | ✘ | ✘ | **✔** | ✘ | ✔ | ✘ | ✘ | ✔ |
| Foundry Project Manager | ✘ | ✘ | ✔ | ✔ (Foundry User only) | ✔ | ✘ | ✔ | ✔ |
| Foundry Account Owner | ✔ | ✔ | **✘** | ✔ | ✔ | ✔ | ✘ | ✘ |
| Foundry Owner | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Owner** | ✔ | ✔ | **✘** | ✔ (any role) | ✔ | ✔ | ✔ | **✘** |
| **Contributor** | ✔ | ✔ | **✘** | ✘ | ✔ | ✔ | ✘ | ✘ |

**Read the Owner row twice.** Owner creates, deletes, deploys models and assigns
any role — and has ✘ on data actions and ✘ on agent endpoints. That single row is
feature 006's `401`, published as a table.

Publishing agents needs **Foundry Project Manager** as a minimum, at the
**Foundry resource** scope.

### Getting started, minimally

Two assignments, both **Foundry User on the Foundry resource**: one to your user
principal, one to your **project's managed identity**. Both are added
automatically when the project is created **through the Foundry portal UI** by
someone who can assign roles — and **not** when the resource is deployed from
SDK or CLI.

That exception is this repository's exact situation: `infra/foundry.bicep`
deploys from the CLI, so nothing is auto-assigned and every role has to be
declared.

### A sample enterprise mapping

| Persona | Role and scope |
| --- | --- |
| IT admin | Owner on the subscription |
| Managers | Foundry Account Owner on the Foundry resource |
| Team lead | Foundry Project Manager on the Foundry resource |
| Developers | **Foundry User on the project** + Reader on the resource |
| Agent consumers | Foundry Agent Consumer on the project, or on a single agent |

---

## 5. Fine-tuning needs both planes

The one scenario where the two-plane split forces a specific answer:

> «To fine-tune a model in Foundry, you need **both data plane and control plane
> permissions**. Deploying a fine-tuned model is a control plane permission.
> Therefore, **the only built-in role with both** data plane and control plane
> permissions is the **Foundry Owner** role. Or, if you prefer, you can also
> assign the **Foundry User** role for data plane permissions and the **Foundry
> Account Owner** role for control plane permissions.»

Two correct answers, and `Owner` is not one of them — its data-action column is
✘, so escalating to subscription Owner does not fix a fine-tuning deployment.

---

## 6. Managed compute has its own control-plane surface

Managed compute deployments (preview) are governed by their own operations under
`Microsoft.CognitiveServices`, mirroring the standard-deployment surface with a
different resource-type segment:

| Operation | Purpose |
| --- | --- |
| `accounts/managedComputeDeployments/read` | read or list |
| `accounts/managedComputeDeployments/write` | create or update |
| `accounts/managedComputeDeployments/delete` | delete |
| `locations/managedComputeCapacities/read` | list available accelerator capacity by region |
| `locations/usages/read` | read accelerator usage and quota consumption |

Role coverage: **Cognitive Services Contributor**, **Foundry Owner** and
**Foundry Account Owner** get all five. **Cognitive Services User**, **Foundry
Project Manager** and **Foundry User** get read + capacities + usages, but not
write or delete.

### The wildcard trap, for anyone writing a custom role

> «A root-level operation `Microsoft.CognitiveServices/capacities/read` does
> **not** exist… A wildcard such as
> `Microsoft.CognitiveServices/locations/*/read` matches `locations/usages/read`
> but **does not match** `locations/managedComputeCapacities/read`. List the
> operation explicitly when authoring a custom role.»

This is the same class of defect as the CI role in `infra/ci-identity.bicep`:
a permission set that compiles, deploys, and then refuses one specific operation
at runtime. `infra/DEPLOY.md` § 5 records the discipline — **add the operation the
error names, never a built-in role.**

### Custom roles

Learn's own example shows the shape — control-plane `actions` and data-plane
`dataActions` in the same definition:

```json
{
  "actions": [
    "Microsoft.CognitiveServices/*/read",
    "Microsoft.Authorization/*/read",
    "Microsoft.CognitiveServices/accounts/listkeys/action",
    "Microsoft.Resources/deployments/*"
  ],
  "dataActions": [
    "Microsoft.CognitiveServices/accounts/AIServices/agents/*"
  ]
}
```

You need **Owner on the resource's scope** to create custom roles there.

⚠️ Note what `listkeys/action` is doing in the control-plane list: **retrieving a
key is a control-plane operation, and the key it returns bypasses the data
plane's RBAC entirely.** A custom role that looks read-only because it only grants
`*/read` plus `listkeys` is, in practice, full data-plane access.

---

## 7. Reading a refusal

| Error | Cause | Fix |
| --- | --- | --- |
| **401 Unauthorized** | missing or expired token; invalid API key | verify the token scope is `https://ai.azure.com/.default`; regenerate the key |
| **403 Forbidden** | missing RBAC role assignment | assign the appropriate role (e.g. Foundry User) at resource or project scope |
| `AADSTS700016` | application not found in tenant | wrong tenant or client ID |
| «Custom subdomain required» | the resource is being reached on a regional endpoint | configure a custom subdomain — **token auth requires one** |

Two other permission facts that are easy to hit and hard to guess:

- **Viewing and purging deleted Foundry accounts** requires **Contributor at
  subscription scope**.
- **Resources created outside Foundry** need their own grants — a new blob
  storage account needs the Foundry account's managed identity in **Storage Blob
  Data Reader**; a new AI Search source needs Foundry added to its role
  assignments.

---

## 8. What this note would cost to verify

**Almost all of it is free, and most of it is already spent.** Role definitions
are readable offline; role assignments cost nothing; the refusals that teach the
most — `401` on chat completions with Owner, and the deliberately-unfixed
connection read — were both produced by feature 006 for the price of two API
calls.

The unexercised parts:

- **Managed compute control-plane operations** (§ 6) — the deployments themselves
  run on dedicated GPU VMs at 3.47–6.94 €/hour (`foundry-cost-model.md` § 2). The
  *permission surface* can be read and a custom role authored for free; creating a
  deployment cannot.
- **Custom roles** — free to write and review, and one was deliberately *not*
  created in feature 006 because «a one-action custom role would be an
  authorization-provider object that survives `az group delete`». That reasoning
  is a cost decision about residue, not about euros, and it still holds.
- **Agent-scope assignments** (`foundry-resource-model.md` § 2) — free, and
  untested here, because no agent has ever been created in this subscription.

---

## Sources

- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry) — read 2026-08-21; §§ 3–6
- [Authentication and authorization in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/authentication-authorization-foundry) — read 2026-08-21; §§ 1, 2, 7
- `online-endpoints.md` § 3, `network-isolation.md` § 3 — the same split on two other services
- `genaiops/foundry-block3/README.md` — the `401`, and the role name now superseded
- `infra/DEPLOY.md` § 5 — the least-privilege discipline referenced in § 6
