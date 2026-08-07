# AI-MLOps-GenAIOps

This is my hands-on preparation repository for **Microsoft AI-300 —
Operationalizing Machine Learning and Generative AI Solutions**. I use it to
build the exam topics as working artifacts instead of reading about them, so
everything here is something I can run, validate, and explain.

I develop it on an Azure free trial, which shapes most of my design decisions:
cheapest viable SKU, nothing left running, and as much validated locally as
possible before anything touches Azure.

## How I work

I drive this repository spec-first, using [GitHub Spec Kit](https://github.com/github/spec-kit)
with Claude Code as the implementation tool.

For each unit of work I write a specification containing the objective, the
requirements, and — the part I care most about — **success criteria that a
command can verify**. Not "the template should be correct", but
`az bicep build` exits 0 and the compiled output contains exactly 2 resources.
Claude Code implements against that spec; I review the diff, run the validation
myself, and authorize every commit individually. Nothing is committed or pushed
on my behalf without my explicit approval.

The rules I hold this repo to are written down in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md). The ones
that bite most often:

- **Cost discipline** — every exercise declares whether it runs locally (free) or
  needs Azure, and anything that could add cost gets flagged with an estimate
  before it is built.
- **Validation before commit** — no IaC or CI change is proposed for commit until
  its validation step actually passes.
- **Source of truth only** — generated artifacts are never tracked in git.

This is deliberate practice for me: the interesting skill is not getting an agent
to produce code, it is specifying work precisely enough that correctness becomes
checkable, and then actually checking it.

## What is built so far

### `infra/` — Azure baseline (Bicep)

A minimal but opinionated baseline: a Storage Account and a Key Vault.

The decisions I made and why:

- **Key Vault uses RBAC authorization**, not access policies — the access-policy
  model is legacy and does not compose with Azure's wider identity story.
- **The tenant ID is never hardcoded.** It comes from `subscription().tenantId`,
  so the template is portable across tenants.
- **Resource names are generated** with `uniqueString(resourceGroup().id)`,
  because storage account and vault names must be globally unique.
- **Soft delete with 90-day retention and purge protection enabled** — purge
  protection is irreversible once on, which is exactly the kind of one-way door
  worth understanding before an exam asks about it.
- **`Standard_LRS` and TLS 1.2 minimum** — the cheapest redundancy tier is the
  right default for learning; the TLS floor is not something to leave at default.

I then extended the baseline with an Azure ML workspace, plus the Application
Insights and Log Analytics resources it depends on.

- **No Container Registry.** The workspace can provision one for itself, and I
  did not let it: roughly $5/month for something no exercise needs yet. The
  property is simply absent from the template rather than set to null.
- **A system-assigned managed identity**, because the exam objective on identity
  is the reason this workspace exists at all. The Key Vault was already on RBAC,
  so granting roles to that identity is the natural next step — no secrets,
  nothing to rotate.
- **Application Insights is workspace-based, so a Log Analytics workspace came
  with it.** Classic Application Insights is retired; a component without a
  backing workspace still compiles but is rejected on deployment. This is why
  the template has five resources and not the four I first specified — I changed
  the spec rather than ship something that only looked correct.
- **I did not take the newest API version for Log Analytics.** The provider
  offers `2026-03-01`, but no Bicep release has type definitions for it yet, so
  using it means `az bicep build` stops checking that resource's properties. I
  took `2025-07-01` instead: eight months older, fully type-checked. Validation
  I can actually run beats a newer version number.

Everything above was validated locally with `az bicep build` before anything
touched Azure.

The compiled ARM JSON is **not** tracked. `main.bicep` is the source of truth and
the JSON is a build artifact, so it lives in `.gitignore`.

### The first deployment

I have since deployed this template for real, into a throwaway resource group.
[`infra/DEPLOY.md`](infra/DEPLOY.md) is the runbook: I wrote it before the
deployment and revised it immediately afterwards, so every expected value in it
is now an observed one.

The deployment is what taught me the difference I had until then only been
asserting. Two defects were latent in a template that compiled without a single
warning and had passed CI:

- **The storage account name was one character over its limit.** `ai300storage`
  plus a 13-character `uniqueString()` is 25 characters, against a hard cap of
  24. I had checked name length for the ML workspace and generalised from it —
  and the storage account turns out to have the tightest limit of the five.
  Bicep does not validate name length at all.
- **`managedNetwork` was left to a service default I had never actually seen.**
  I assumed `what-if` would reveal it. It does not: `what-if` renders what the
  template declares, not what the resource provider applies at creation time.
  The stake was not academic — `AllowOnlyApprovedOutbound` provisions a managed
  firewall billed hourly whether or not anything uses it. The template now pins
  `Disabled` explicitly.

Two further things were decided by the subscription rather than by the template:
`westeurope` rejects every resource here with `RequestDisallowedByAzure`, a
capacity restriction Azure applies to new customers, which is why the default
region is now `northeurope`; and all five resource providers started out
unregistered, which fails a deployment immediately.

At rest this deployment should cost approximately nothing — none of the five
resources carries a fixed monthly fee. I am checking that in Cost Management
rather than trusting the table, because a figure that is not near zero would
mean something was provisioned that the template never declared.

So the template compiles, and it also deploys. Those turned out to be genuinely
different claims.

### `.github/workflows/` — continuous validation

A GitHub Actions workflow that recompiles the Bicep template on every push and
pull request touching `infra/`.

It deliberately **requires no Azure credentials and performs no deployment**.
This is syntactic and semantic validation only, which means it costs nothing,
needs no secrets in the repository, and cannot accidentally provision anything.
Azure CLI is preinstalled on GitHub's Ubuntu runners, so the job only installs
the Bicep module and runs the build — a non-zero exit fails the job.

## What is planned

These areas are scaffolded but not yet built out. They will appear here as I work
through the exam objectives:

| Folder              | Scope                                        |
| ------------------- | -------------------------------------------- |
| `mlops/`            | Classical ML operationalization              |
| `genaiops/`         | Generative AI operationalization             |
| `qa-observability/` | Quality assurance, monitoring, observability |
| `rag-optimization/` | Retrieval-augmented generation               |
| `docs/exam-notes/`  | AI-300 study notes                           |

## Running the validation locally

```bash
az bicep install
az bicep build --file infra/main.bicep
```

An exit code of 0 means the template compiles. This requires no Azure
subscription and costs nothing — it is the same check the CI workflow runs.
