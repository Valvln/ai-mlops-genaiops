# AI-MLOps-GenAIOps

This is my hands-on preparation repository for **Microsoft AI-300 —
Operationalizing Machine Learning and Generative AI Solutions**. I use it to
build the exam topics as working artifacts instead of reading about them, so
everything here is something I can run, validate, and explain.

I develop it on a Pay-As-You-Go subscription with the spending limit off. I
spent the first three features believing it was a free trial, and checking
turned out to matter: no credit absorbs these figures, and nothing stops a bill
automatically. That is what my design decisions are actually protecting against
— cheapest viable SKU, nothing left running, and as much validated locally as
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
resources carries a fixed monthly fee. I checked that in Cost Management rather
than trusting the table, because a figure that is not near zero would mean
something was provisioned that the template never declared. It is zero: only the
storage account and the vault have usage records at all, both at no charge.

The resource count, on the other hand, was wrong. My runbook said the group
should contain five resources; it contains six. Application Insights deployed a
notification group for itself ten minutes after the workspace — its own
deployment, which I did not ask for and which is recorded in the deployment
history as having failed. It costs nothing, but it is the same habit that later
defeated the identity work below: this platform provisions things the template
never mentions.

So the template compiles, and it also deploys. Those turned out to be genuinely
different claims.

### What the workspace identity taught me — a feature that failed

Let's name the failure upfront: I tried to shrink a managed identity down to only what it needed. I did not succeed — and I am keeping the attempt in the repository, because the reason it failed is worth more than the feature would have been.

The identity already held four role assignments no template had ever declared, one of them a wildcard grant over the whole resource group. So the task was never "grant the minimum"; it was "take back what had been granted without asking."

Two assumptions fell apart along the way. Empty credentials, I learned, mean the tool hides them — not that the data stores don't use them. And one of my success criteria could never have passed: even the old, already-deployed template showed changes on a clean run. Comparing against that baseline before trusting any result is the one habit worth keeping.

Then the real lesson. I removed the platform's grant; it quietly recreated it under a new name. I told it to stop assigning permission at the resource-group level; it obeyed the letter and split one broad grant into three narrow ones — same authority, better disguised. One of my checks turned green on exactly that outcome, because it was only ever reading a word in a scope string, not the reach it claimed to measure. A test can pass while the thing it exists to guarantee never happens.

The honest conclusion is negative: these permissions are the platform's to manage, not mine to trim. A user-assigned identity might escape that — but it stays written down as a question, not an answer, and I am not spending a session to settle it. I have to rebuild this workspace anyway when the vault's 90-day trap forces a new resource group; changing one line of Bicep then costs nothing. Deferring a cheap experiment until it becomes free is itself a decision worth making on purpose.

What the attempt did leave behind is real: the workspace now authenticates through its own identity instead of account keys, the reasoning is on record for whoever reads this next, and it cost nothing to learn.

The template still declares exactly one role assignment, on the Key Vault, and it does nothing — the platform's own grant already covers it. I kept it anyway, with a comment that says so in the first line. It is where the working mechanics live: a deterministic name so redeployment is idempotent, an explicit principal type, no subscription id written down. Deleting it would have been tidier and would have taught the next reader less.

So the next thing I build is not another attempt at this. It is the opposite case: a deployment identity for CI, through OIDC and federated credentials — a service principal I create, with a role I assign, at a scope I choose. Same exam objective, and this time least privilege is actually reachable. Holding those two side by side is what I expect to make the difference when a question asks which identity belongs where.

### Deployment from CI, without a stored secret

I followed through on the previous phase's promise: same question, but with my own identity in place of the platform's. CI now deploys `main.bicep` authenticating over OIDC. There is no password and no certificate in the repository — they were never created, and I checked that after the deployment had already succeeded.

The method was failing on purpose: I seeded the role with the eight operations the activity log had recorded, and let the deployment break five times; each error named what was missing, and I added only that. Two instructive errors: one put back an operation I had removed myself; the other was a successful deployment with a red run. Green does not prove something was deployed; red does not prove it wasn't.

Then an interesting part: four commands that must be refused run inside the workflow on every deploy, and one of those four, the first time, passed without testing anything. Right exit code, right error class, wrong axis. I only saw it by reading the error instead of the green summary — a genuinely useful lesson.

The same trap came back a third time, when I wanted to prove the grant is actually doing something. Withdrawing it and redeploying does fail — but it fails with "no subscriptions found". It took three attempts to get a real denial: every `az` command resolves something locally before asking Azure, and every local resolution is a failure. In the end it came out as an HTTP request: 403 without the grant, 201 with it, same request. That is the check 002 would not have passed.

### Somewhere to read from, something to run on

The workspace existed but could do nothing — no data, no compute. This feature gave it both: a blob container, a datastore that authenticates as the workspace instead of holding a key, a cluster that scales to zero when idle. All declared in the template, all shipped through CI and the approval gate.

Widening the role again corrected an assumption I had carried since the earlier work: that failures arrive one at a time. This run named three missing permissions at once — because validation checks the whole template before submitting any of it, while my earlier failures had only ever surfaced singly, during execution. "One per run" was never a rule. It was a symptom I had mistaken for one.

Two refusals then arrived in different costumes: AuthorizationFailed from ARM, UserError from Azure ML's own front end — same meaning, different name, and only one looks like a permissions problem on sight.

The measurements corrected me further. A cluster at rest consumes no vCPU quota at all; quota counts what is running, not what the template allows — quota and cost, it turns out, are two separate ledgers, and I had been reading one to predict the other. I also went looking for the networking resources the design notes promised. They were never there. The grant I had justified by their existence was withdrawn, and nothing broke.

One criterion I could not close — my error, not the deployment's: I asked for cost data the same day, and cost data arrives roughly a day late. A criterion that cannot be checked when the work ends will quietly go unchecked. I scheduled it instead, and wrote the question down.

### `.github/workflows/` — validation and deployment

**`bicep-validate.yml`** — recompiles every template under `infra/` on every push
and pull request touching it. No Azure credentials, no deployment, no token
permissions beyond reading the repository. A fork's pull request runs it
unchanged.

**`infra-deploy.yml`** — deploys `main.bicep` on a merge to `main` or on manual
dispatch. Authenticates over OIDC against a federated credential bound to the
`azure-deploy` environment, so a run that has not passed the approval gate cannot
obtain a token. A second job runs the four boundary probes as assertions; a probe
that succeeds fails the run.

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
for template in infra/*.bicep; do az bicep build --file "$template"; done
```

An exit code of 0 means the templates compile. This requires no Azure
subscription and costs nothing — it is the same check `bicep-validate.yml` runs.
