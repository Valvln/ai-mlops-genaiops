# Feature Specification: Block 3 — Azure AI Foundry GenAIOps backbone

**Feature Branch**: `006-foundry-genaiops`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Block 3 — Azure AI Foundry GenAIOps: the smallest
deployment that exercises AI-300 Domain 3 exam objectives (model deployment,
versioned prompts, traced calls), verified deployable and priced before being
built."

## Context

Block 2 (classical ML, `infra/main.bicep`) closed at 933/1000 on its retest.
Block 3 opens Domain 3 — Generative AI operationalization on Azure AI Foundry —
as a new, independent feature. Unlike blocks 1–2, this feature does not extend
`infra/main.bicep`: it targets a different region for a reason that is itself
exam material, not incidental.

### Why this isn't a `northeurope` extension of the existing backbone

`az cognitiveservices model list -l <region>`, a read-only and free command, was
run against both `northeurope` and `swedencentral` before this feature was
scoped (recorded in `docs/exam-notes/foundry-cost-model.md` § 4, dated
2026-08-18). In `northeurope`, every deployable chat model is offered only as
`GlobalProvisionedManaged` — a PTU SKU, which this project's cost constraint
rules out categorically (§ Cost, below). `swedencentral` offers the same models
as `Standard` or `GlobalStandard`. Region eligibility for *this* subscription
was confirmed separately and for free, this session: a `what-if` against a
minimal `Microsoft.CognitiveServices/accounts` probe in `swedencentral`
returned `status: Succeeded`, `changeType: Create`, with no
`RequestDisallowedByAzure` — the same failure mode that rules out `westeurope`
for this subscription (`infra/DEPLOY.md` § 0.2) does not apply here.

`infra/main.bicep` and its resource group keep their `northeurope` region
unchanged. This feature's resources are new and separate.

### Non-negotiable constraints (decided before this spec, not reopened here)

1. **Foundry resource + Foundry project only. No hub.** A hub
   (`Microsoft.MachineLearningServices/workspaces`, kind `hub`) provisions
   dependencies on creation — including a container registry that cannot be
   detached and bills at rest — the same mechanism that has already cost this
   project money twice (`infra/DEPLOY.md`, "The registry the workspace
   attached"). The lean path (Foundry account + Foundry project) creates
   nothing that bills while idle.
2. **Model deployment must be per-token (Standard or GlobalStandard) only.**
   Never PTU, never provisioned, at any stage — including drafts. A provisioned
   deployment's minimum floor is documented at ≈316 €/day and cannot be paused;
   it can only be stopped by deletion (`foundry-cost-model.md` § 3b).
3. **Azure AI Search: Free tier or not created at all.** Out of scope for this
   feature regardless (see Assumptions) — recorded here because it is a
   standing guardrail for whatever feature adds retrieval next, not because
   this feature touches AI Search.
4. **Nothing that bills while idle is created before its daily rate and its
   deletion command are written down.** This spec's Cost section satisfies that
   for everything it proposes to create.
5. **Region is `swedencentral` for this feature's resources.**
   `infra/main.bicep`'s region (`northeurope`) is not touched.

## Cost

Stated up front per constitution Principle I. Every resource this feature
proposes is checked against "does it bill at rest", the question
`foundry-cost-model.md` § 2 recommends over raw price:

| Resource this feature creates | Bills while idle? | Daily rate while idle | Deletion command |
| --- | --- | --- | --- |
| Foundry account (`Microsoft.CognitiveServices/accounts`, kind `AIServices`) | **no** — usage only | €0.00 | `az cognitiveservices account delete` |
| Foundry project (subresource of the account) | **no** — subresource, no independent billing | €0.00 | deleted with the account |
| One model deployment, Standard/GlobalStandard SKU | **no** — meter runs only while a request is in flight, stops when the request ends | €0.00 | `az cognitiveservices account deployment delete` |
| The dedicated resource group itself | **no** — a resource group has no charge of its own | €0.00 | `az group delete --name <rg> --yes` |

**Nothing this feature creates bills at rest.** The only cost is tokens actually
consumed by test calls: at the rates recorded in `foundry-cost-model.md` § 4 for
`swedencentral` (e.g. `gpt-5-nano`, ≈0.044 €/1M input, ≈0.351 €/1M output), a
generous budget of 10M input + 2M output tokens for the whole feature costs
**≈1.14 €**. A realistic exercise budget (a handful of manual test calls plus
whatever the tracing checks require) is expected to land under **0.20 €**.

No AI Search, no hub dependency, no reserved/provisioned throughput, and no
fine-tuning are part of this feature — the four line items in
`foundry-cost-model.md` § 2 that do bill while idle or at a punishing rate are
all excluded by construction, not by discipline applied after the fact.

## Clarifications

None raised. Every fork with more than one reasonable answer (deployment
mechanism, exact model choice, tracing implementation, resource group
placement) has a documented default in Assumptions below, and none of them
changes this feature's scope, its cost profile, or which exam objectives it
exercises — the tests in the guidance for using
`[NEEDS CLARIFICATION]` markers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A token-billed model answers a call (Priority: P1)

The author needs one Azure AI Foundry model deployment that responds to a real
request, deployed in a way that is provably never billed by the hour. This is
the smallest possible round trip and the precondition for everything else in
the block: prompt versioning and call tracing both need something to call.

**Why this priority**: Without a working per-token deployment, there is nothing
to version prompts against or trace calls through. This is the block's MVP.

**Independent Test**: Fully testable by deploying the model, sending one
request, and reading back both the response and the deployment's own SKU. No
prompt file and no trace query need exist yet for this story to demonstrate
value on its own.

**Acceptance Scenarios**:

1. **Given** a Foundry account and project exist in `swedencentral` with no
   model deployment yet, **When** one chat-capable model is deployed, **Then**
   its SKU, read back from the service, is `Standard` or `GlobalStandard` —
   never a PTU-family SKU (`ProvisionedManaged`, `GlobalProvisionedManaged`,
   `DataZoneProvisionedManaged`).
2. **Given** the deployment exists, **When** a single completion request is
   sent to it, **Then** a response is returned and the request's cost is
   attributable to tokens consumed, not to a standing hourly charge.
3. **Given** the deployment has existed for a period with no requests sent,
   **When** its billing is checked, **Then** the observed charge for that idle
   period is €0.00.

---

### User Story 2 - The prompt behind a call is a versioned file (Priority: P2)

The author needs the prompt used to exercise the model to live in the
repository as a file with real git history, not typed once into the Foundry
portal and forgotten. This is what makes prompt iteration an exam objective
that can be *demonstrated* rather than described: a diff, a commit, and an
old version that can be recovered.

**Why this priority**: Depends on User Story 1 (something to send the prompt
to), and is itself required before User Story 3 can attribute a trace to "which
version of the prompt produced this call."

**Independent Test**: Fully testable by editing the prompt file, committing the
change, and confirming the file's git history shows more than one revision —
independent of whether any trace has been queried yet.

**Acceptance Scenarios**:

1. **Given** a prompt authored as a file under version control, **When** a call
   is made using that prompt, **Then** the call can be traced back to the exact
   file content used, not to an unversioned string typed into a portal.
2. **Given** the prompt file is edited and committed a second time, **When**
   its git history is read, **Then** both revisions are present and diffable.
3. **Given** a prompt edited only inside the Foundry portal's own prompt
   editor (not saved to a file in this repository), **When** it is used for a
   call, **Then** that call does not satisfy this story — portal-only edits are
   not versioned for the purpose of this feature.

---

### User Story 3 - A past call can be traced without having watched it happen (Priority: P2)

The author needs to make a call, walk away, and later retrieve a record of that
specific call — which prompt version was used, which deployment answered, and
what the response was — without relying on terminal scrollback. This is the
monitoring/observability objective of Domain 3, and it is the one most exposed
to the repository's recurring failure mode: a check that passes while proving
nothing (`docs/exam-notes/foundry-cost-model.md`'s sibling specs record this
repeatedly — a green run is not proof of the right thing happening).

**Why this priority**: Depends on User Story 1 for a call to trace, and
benefits from User Story 2 so the trace can name a specific prompt version
rather than an untracked string.

**Independent Test**: Fully testable by making one call, closing the terminal
that made it, and then retrieving that call's record through a separate query
— proving retrieval, not just that output scrolled past once.

**Acceptance Scenarios**:

1. **Given** a call was made and its terminal output is no longer available,
   **When** the call's record is queried afterward, **Then** the record
   returns the prompt version used, the deployment identity, and the response
   content.
2. **Given** two calls were made with two different prompt versions, **When**
   their records are queried, **Then** the two records are distinguishable
   from each other by prompt version, not merely by timestamp.

---

### Edge Cases

- **`swedencentral` stops being eligible after this feature starts** (this
  session's `what-if` probe was clean, but region eligibility has changed for
  this subscription before — see `infra/DEPLOY.md` § 0.2 on `westeurope`).
  Response: re-run `az cognitiveservices model list` against another candidate
  region and choose based on which models are deployable at a token-billed SKU,
  never on latency, never on `northeurope` (already ruled out for chat models).
- **The model chosen at cost-model time (`gpt-5-nano`) is no longer offered, or
  no longer offered at a token-billed SKU, in `swedencentral` by
  implementation time.** Response: re-run
  `az cognitiveservices model list -l swedencentral` at implementation time —
  the 2026-08-18 snapshot is treated as a hypothesis, not a fact, and the
  actual model choice is whatever the fresh query supports.
- **A prompt is edited only in the Foundry portal.** Response: not accepted as
  satisfying User Story 2; the portal is for interactive testing, the
  repository file is the source of truth for versioning.
- **A deployment is accidentally left running at the end of a session.**
  Response: because the SKU is Standard/GlobalStandard, "left running" costs
  nothing while idle by construction (Cost section) — but the resource group
  is still deleted at session close per this project's standing rule (never
  leave compute or endpoints running unattended), verified rather than
  assumed.
- **Cost Management data for the feature's resource group is absent on the day
  it is checked.** Response: read as "no data yet," never as "confirmed free"
  — this project has already drawn the wrong conclusion from an absent row
  once (`infra/DEPLOY.md` § 4).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST create exactly one Foundry account
  (`Microsoft.CognitiveServices/accounts`, kind `AIServices`) and exactly one
  Foundry project as its subresource. It MUST NOT create a hub
  (`Microsoft.MachineLearningServices/workspaces`, kind `hub`) or any resource
  the hub path would provision on its behalf.
- **FR-002**: All resources created by this feature MUST be located in
  `swedencentral`. `infra/main.bicep` and its resource group's region MUST NOT
  be modified by this feature.
- **FR-003**: Exactly one model deployment MUST be created, using a `Standard`
  or `GlobalStandard` deployment SKU. No deployment using a PTU-family SKU
  (`ProvisionedManaged`, `GlobalProvisionedManaged`,
  `DataZoneProvisionedManaged`) may be created at any point, including as an
  intermediate or test step.
- **FR-004**: The specific model deployed MUST be confirmed — by running
  `az cognitiveservices model list -l swedencentral` at implementation time,
  not by trusting the cost model's 2026-08-18 snapshot — to support a
  token-billed SKU in `swedencentral`.
- **FR-005**: This feature MUST NOT create an Azure AI Search resource. If a
  later feature adds retrieval, it inherits the Free-tier-or-nothing
  constraint recorded in Context above; this feature does not need to satisfy
  it because it creates no such resource.
- **FR-006**: The prompt(s) used to exercise the model MUST exist as files
  tracked in this repository's version control, so that a change to a prompt
  is visible as a diff and attributable to a commit.
- **FR-007**: Every call made to the deployed model as part of this feature's
  verification MUST produce a record that is retrievable after the call
  completes — at minimum the prompt version used, the deployment identity, and
  the response — without depending on terminal output captured at the time of
  the call.
- **FR-008**: This feature's resources MUST be deployable, verifiable, and
  destroyable independently of `infra/main.bicep`'s resource group, so that
  one can be torn down without affecting the other.
- **FR-009**: Every resource type this feature proposes to create MUST be
  checked against "does it bill while idle" before it is created, with the
  answer, the daily rate if nonzero, and the deletion command recorded in this
  spec's Cost section — satisfied above for all four resources this feature
  creates.
- **FR-010**: No deployment against the live subscription may happen without
  an explicit action taken by the author in the session it happens; nothing in
  this feature deploys unattended or on a schedule.
- **FR-011**: A read-only dry run (`az deployment group what-if` or
  equivalent) MUST be reviewed against the live subscription before the first
  real deployment of this feature's infrastructure, consistent with
  constitution Principle V.
- **FR-012**: If continuous integration is used to deploy any part of this
  feature, any resource type not already covered by the CI deployer role
  (`infra/ci-identity.bicep`) MUST be added only as the exact operation a
  failing run names, with that run's id recorded as provenance — never by
  widening the role with a built-in role definition, per `infra/DEPLOY.md` §
  5.

### Key Entities

- **Foundry account**: the top-level Azure AI Foundry resource in
  `swedencentral`; billed only for usage that flows through it, never for
  existing.
- **Foundry project**: a child of the Foundry account; the workspace-like
  container the model deployment, prompts, and traces are organized under.
- **Model deployment**: a named, versioned binding of a specific model to a
  specific deployment SKU (`Standard`/`GlobalStandard`) inside the Foundry
  project; the unit that is billed per token.
- **Prompt (versioned)**: a file tracked in this repository, identified by its
  git history, that supplies the text sent to the model deployment for a given
  call.
- **Call trace**: a retrievable record of one request to the model deployment,
  linking the prompt version used, the deployment identity, and the response
  received.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `az cognitiveservices account deployment show` (or equivalent)
  read against the live model deployment reports a SKU name of `Standard` or
  `GlobalStandard` — checked by command, not by what the deployment request
  asked for.
- **SC-002**: A single completion request sent to the deployment returns a
  successful response, verified by the command or script that sent it and its
  captured HTTP status.
- **SC-003**: `git log --follow` (or equivalent) on the prompt file used for
  testing returns at least two revisions after this feature's first iteration
  cycle, proving the prompt was edited as a tracked file and not typed once
  into a portal.
- **SC-004**: For at least one call made during this feature's verification,
  its trace record is retrieved by a query run in a session separate from the
  one that made the call, and that record names the correct prompt version and
  deployment.
- **SC-005**: `az resource list` against this feature's dedicated resource
  group, run after deployment and before any test calls, shows no resource
  type other than the Foundry account (and its project subresource, if it
  surfaces as a listed resource) — confirming nothing beyond FR-001's two
  resources exists.
- **SC-006**: The measured at-rest daily cost of this feature's resource
  group, read from Cost Management after data is available (not assumed on
  the day of deployment — see Edge Cases), is **€0.00** for any day with zero
  completion requests sent.
- **SC-007**: `az group delete --name <this feature's resource group> --yes`,
  followed by `az resource list` scoped to that group, leaves zero resources —
  confirming the whole feature is removable in one command with nothing left
  behind.

### Deferred Criteria

Declared here rather than discovered at closing time — the pattern feature 005
established after closing with a criterion it could not read on the day it was
scheduled (Cost Management data lags ingestion by roughly 8–24 hours, per
`infra/DEPLOY.md` § 4).

| Criterion | Depends on | Readable from |
| --- | --- | --- |
| SC-006 — measured at-rest cost | Cost Management data for the deployment day | the day after deployment |

## Assumptions

- **A new, dedicated resource group hosts this feature**, separate from
  `infra/main.bicep`'s resource group. This follows from FR-008 (independent
  teardown) and the region split already decided (Context): resources in a
  different region serving a different exam domain do not need to share a
  lifecycle with the classical-ML backbone. Its exact name is a plan-level
  detail.
- **This feature is deployed by the author running `az deployment group
  create` directly, not through the existing GitHub Actions pipeline.** The
  existing pipeline's CI role is deliberately scoped to one resource group and
  grows one named operation at a time (`infra/DEPLOY.md` § 5); routing a new,
  exploratory, differently-regioned feature through it would mean widening
  that role's blast radius to a second resource group for infrastructure that
  is meant to be small and disposable. A manual deployment, authorized by the
  author at the moment it runs, satisfies FR-010 without that widening. FR-012
  is kept in case this default is revisited at plan time.
- **The exact model deployed is chosen at implementation time** from whatever
  `az cognitiveservices model list -l swedencentral` reports as token-billed
  at that moment (FR-004), not fixed here to `gpt-5-nano` — the cost model's
  figures for that model are used only to size the budget in the Cost section.
- **The mechanism used to make call traces retrievable (FR-007) is a
  plan-level choice** — for example Foundry's own tracing surface, or
  Application Insights attached to the project. The spec requires only that a
  trace be retrievable after the fact, not by which service.
- **No embeddings model is deployed.** The stated objective names "the model"
  (singular) alongside the prompt and the trace; a second deployment would
  double the SKU-eligibility and cost bookkeeping for no exam objective this
  feature is scoped to cover.
