# Feature Specification: Block 4 — GenAI QA and Observability

**Feature Branch**: `007-genai-eval-observability`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "Block 4 — GenAI QA and Observability (AI-300 Domain 4): the
smallest set of evaluation and quality-metric artifacts that build on Block 3's
traced-call foundation (feature 006, genaiops/foundry-block3), verified deployable,
bounded in call volume, and priced before being built."

## Context

Block 3 (spec 006, `genaiops/foundry-block3/`) closed having proved three things: a
model deployment billed strictly per token, a prompt versioned as a tracked file, and
a call whose record survives the process that made it — `call_model.py` emits an
OpenTelemetry span carrying the prompt's git revision, and `query_trace.py` reads that
span back from Application Insights / Log Analytics, as a separate invocation. Block 4
opens AI-300 Domain 4 — quality assurance and observability for generative AI — as the
next feature to sit on top of that call-and-trace mechanism, not as a new mechanism to
invent. Where block 3 asked "can I prove which prompt produced a given answer", block 4
asks "can I prove whether that answer was any good, and can I see that judgment later
without having watched it happen."

### The Foundry deployment this feature depends on no longer exists

Block 3's resource group, `rg-ai300-foundry`, was torn down at that feature's close
(its own SC-007 required exactly that — zero resources left after
`az group delete`). This spec does not assume any Foundry account, project, or model
deployment currently exists. Delivering this feature requires redeploying
`infra/foundry.bicep` from an empty resource group, and that redeployment's own success
is itself evidence, not just a precondition: it is the second time this project's
Bicep has been asked to recreate, unattended by any manual portal fix, exactly what it
describes — the first being `infra/main.bicep`'s from-scratch rebuild of
`rg-ai300-test01` on 2026-08-18 (`infra/DEPLOY.md`, measured at 317 s teardown and a
full redeploy afterward). A template that only ever deploys once, into a resource group
that is never actually gone, has not proven it is a template.

### Non-negotiable constraints (decided before this spec, not reopened here)

1. **Region `swedencentral`, exactly as block 3 used**, for the same reason recorded in
   `docs/exam-notes/foundry-cost-model.md` § 6: `northeurope` cannot deploy a
   token-billed chat model at all (PTU only), and `swedencentral` can. This feature does
   not re-derive that decision.
2. **Model deployment must be per-token (Standard or GlobalStandard) only.** Never PTU,
   never provisioned, at any stage including drafts — the same rule spec 006 already
   established (`foundry-cost-model.md` § 6, item 2), and for the same reason: a
   provisioned deployment's floor is documented at ≈316 €/day and cannot be paused, only
   deleted.
3. **No hub.** `Microsoft.MachineLearningServices/workspaces` (kind `hub`) is excluded by
   construction, as in block 3 — it provisions a container registry that cannot be
   detached and bills at rest regardless of use.
4. **Nothing that bills while idle is created before its daily rate and its deletion
   command are written down** in this spec's Cost section, first — the same discipline
   block 3's spec applied to itself.
5. **The environment is disposable by design.** This feature's resources are meant to be
   built, exercised, and torn down within a session; teardown is a success criterion
   (see SC-007 below), not a closing note added after the fact.

## Cost

Stated up front per constitution Principle I. Every resource this feature proposes is
checked against "does it bill at rest" — `foundry-cost-model.md` § 2's question — before
being created.

| Resource this feature creates | Bills while idle? | Daily rate while idle | Deletion command |
| --- | --- | --- | --- |
| Foundry account (`Microsoft.CognitiveServices/accounts`, kind `AIServices`), redeployed from `infra/foundry.bicep` | **no** — usage only | €0.00 | `az cognitiveservices account delete` |
| Foundry project (subresource of the account) | **no** — subresource, no independent billing | €0.00 | deleted with the account |
| One model deployment, Standard/GlobalStandard SKU | **no** — meter runs only while a request is in flight | €0.00 | `az cognitiveservices account deployment delete` |
| Log Analytics workspace + Application Insights, redeployed with the account (block 3's trace store; block 4 reuses it rather than standing up a second one) | **no** — consumption only, first 5 GB/month free | €0.00 | deleted with the resource group |
| The dedicated resource group itself | **no** — a resource group has no charge of its own | €0.00 | `az group delete --name <rg> --yes` |
| Evaluation records (scored transcripts, groundedness verdicts) | **no** — stored as spans/attributes in the trace store above, or as files in this repository; neither is a billed resource type in its own right | €0.00 | deleted with the resource group, or with the file |

**Nothing this feature creates bills at rest.** The only cost is tokens actually
consumed — both by the calls being evaluated and, if an LLM-as-judge approach is used
for a quality metric, by the judge's own calls. This is where block 4's cost profile
genuinely differs from block 3's, and the difference is sized explicitly:

Block 3 measured its total spend directly rather than estimating it: six calls, all
token-billed, totaled **€0.001039**. Block 4's purpose is automated evaluation — running
a quality check across more than one prompt variant, more than one test question, and
possibly a judge call per response — which multiplies the call count by construction,
not by accident. At `foundry-cost-model.md` § 4 rates for the cheapest deployable model
in `swedencentral` (`gpt-5-nano`, ≈0.044 €/1M input, ≈0.351 €/1M output), even a
generous 500-call verification run, averaging 500 input + 200 output tokens per call,
costs 500 × (500×0.044 + 200×0.351)/1,000,000 ≈ **€0.045** — still a rounding error in
absolute euros. The risk this feature's Cost section exists to name is not "this gets
expensive," it is "this silently stops being negligible if nobody bounds it" — which is
why SC-006 below puts a numeric ceiling on invocation count rather than trusting the
euro figure alone to stay small.

## Clarifications

None raised. The mechanism for scoring quality (a fixed rubric, an LLM-as-judge, a
programmatic groundedness check against source text) is a plan-level choice with more
than one reasonable default and no scope, cost, or exam-objective impact regardless of
which is picked — recorded as an Assumption below rather than as a
`[NEEDS CLARIFICATION]` marker.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A response gets a quality score attached to its trace (Priority: P1)

The author needs a call's response evaluated against at least one quality dimension —
for example groundedness, or relevance to the question asked — and that evaluation
result attached to the same retrievable record block 3 already proved exists. This is
the smallest unit of Domain 4 value: without a score attributable to a specific call,
there is nothing to aggregate, compare across prompt versions, or alert on.

**Why this priority**: Every other story in this feature depends on evaluation results
existing and being retrievable; this is the block's MVP, the same role User Story 1
played in spec 006.

**Independent Test**: Fully testable by sending one call, running one evaluation against
its response, and confirming the evaluation result is retrievable by a query naming that
specific call — independent of whether more than one prompt variant or more than one
metric exists yet.

**Acceptance Scenarios**:

1. **Given** a call has been made to the redeployed model deployment and its response
   captured, **When** an evaluation is run against that response, **Then** a quality
   result (a score, a pass/fail verdict, or both) is produced and is retrievable,
   identified by the call it evaluated.
2. **Given** an evaluation result has been recorded, **When** it is queried in a session
   separate from the one that produced it, **Then** the result names which call it
   belongs to, which prompt version produced that call (reusing block 3's
   `prompt.version` attribute), and the score or verdict itself.
3. **Given** no evaluation has yet been run for a given call, **When** that call's trace
   is queried, **Then** the absence of an evaluation result is distinguishable from an
   evaluation that ran and scored zero — silence is never read as a passing or failing
   score.

---

### User Story 2 - Two prompt variants are compared on the same metric (Priority: P2)

The author needs to change a prompt, as in block 3's revision history, and see whether
the change moved a quality metric — not just whether the model still returns fluent
text. This is what turns prompt iteration from "the wording looks better" into a
decision supported by a measurement, and it is the exam objective this story exists to
demonstrate: comparative evaluation across prompt versions.

**Why this priority**: Depends on User Story 1 for a working evaluation mechanism; two
scores from one version cannot be compared to anything. Ranked below User Story 1
because a single scored call already demonstrates the core mechanism works before this
story asks it to run twice.

**Independent Test**: Fully testable by evaluating the same test question against two
committed prompt revisions and confirming the two evaluation results are distinguishable
by which prompt version produced them — independent of whether groundedness (User Story
3) is one of the metrics used.

**Acceptance Scenarios**:

1. **Given** two committed revisions of the same prompt file, **When** each is used to
   answer the same test question and each response is evaluated, **Then** the two
   evaluation results are retrievable side by side, each attributed to its own prompt
   revision.
2. **Given** the two evaluation results differ, **When** the comparison is reviewed,
   **Then** the direction of the difference (which revision scored higher on which
   metric) is stated, not left for the reader to infer from raw numbers alone.

---

### User Story 3 - A response is checked for groundedness against its source (Priority: P2)

The author needs at least one evaluation that is not a general fluency or relevance
judgment but specifically checks whether a response's claims are supported by the
material it was supposed to be answering from. This is the groundedness objective named
explicitly in Domain 4, and it is a different failure mode than "the answer is
unhelpful" — a fluent, relevant, confidently wrong answer is the one this story exists
to catch.

**Why this priority**: Depends on User Story 1 for the scoring mechanism to exist.
Ranked alongside User Story 2 rather than above it because both are extensions of the
same MVP in different directions, and neither blocks the other.

**Independent Test**: Fully testable by evaluating one response known to contain an
unsupported claim and confirming the groundedness check flags it, alongside one response
known to be fully supported and confirming it is not flagged — independent of whether
prompt-variant comparison (User Story 2) has been exercised.

**Acceptance Scenarios**:

1. **Given** a response whose claims are fully supported by its source material, **When**
   the groundedness check runs, **Then** it records a passing verdict.
2. **Given** a response containing at least one claim not supported by its source
   material, **When** the groundedness check runs, **Then** it records a failing verdict,
   distinguishable from the passing case in User Story 1's Acceptance Scenario 3 sense —
   not merely a lower number on the same unbounded scale.

---

### Edge Cases

- **The evaluation mechanism itself makes model calls (LLM-as-judge) and those calls are
  not counted toward the invocation cap.** Response: every call this feature's
  verification makes — the calls being evaluated and the judge's own calls, if any —
  counts toward SC-006's ceiling; a judge call is not exempt because it evaluates rather
  than answers.
- **`swedencentral` or the specific model chosen stops being eligible before this feature
  is implemented.** Response: identical to block 3's edge case — re-run
  `az cognitiveservices model list -l swedencentral` at implementation time and treat any
  earlier snapshot as a hypothesis, never a fact.
- **An evaluation run is interrupted partway (process killed, network failure) after some
  but not all calls completed.** Response: partially completed evaluation results are
  retrievable and distinguishable from a complete run by count, so a partial run is never
  mistaken for a full comparison — the same "a check that passes while proving nothing"
  failure mode block 3's README names explicitly.
- **The invocation cap (SC-006) is reached before all planned evaluations complete.**
  Response: the run stops rather than silently exceeding the cap; whatever evaluation
  results exist up to that point remain valid and retrievable for the calls actually
  made.
- **Cost Management data for this feature's resource group is absent on the day it is
  checked.** Response: read as "no data yet," never as "confirmed free" — the same
  standing rule spec 006 recorded after this project drew the wrong conclusion from an
  absent row once (`infra/DEPLOY.md` § 4).
- **A deployment or evaluation run is left going at the end of a session.** Response:
  because the SKU is Standard/GlobalStandard, an idle deployment costs nothing by
  construction — but the resource group is still deleted at session close per this
  project's standing rule, verified rather than assumed (SC-007).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST redeploy `infra/foundry.bicep` into a resource group
  containing no pre-existing Foundry resources, and MUST confirm the redeployment
  succeeded before any evaluation work depends on it.
- **FR-002**: All resources created or reused by this feature MUST be located in
  `swedencentral`. `infra/main.bicep` and its resource group's region MUST NOT be
  touched by this feature.
- **FR-003**: The model deployment used for this feature's calls MUST use a `Standard` or
  `GlobalStandard` deployment SKU. No PTU-family SKU
  (`ProvisionedManaged`, `GlobalProvisionedManaged`, `DataZoneProvisionedManaged`) may be
  created at any point, including as an intermediate or test step.
- **FR-004**: The feature MUST produce, for at least one call, a quality evaluation
  result that is retrievable after the fact and attributable to that specific call and
  the prompt version that produced it, reusing block 3's `prompt.version` attribute
  rather than inventing a parallel identifier.
- **FR-005**: The feature MUST include at least one groundedness check — an evaluation
  that specifically assesses whether a response's claims are supported by its source
  material, distinct from a general quality or relevance score.
- **FR-006**: The feature MUST demonstrate comparison of evaluation results across at
  least two committed revisions of the same prompt file, with each result attributed to
  the revision that produced it.
- **FR-007**: Every evaluation this feature performs as part of its verification MUST be
  counted, and the total count MUST be checked against the numeric ceiling in SC-006
  before the verification is considered complete.
- **FR-008**: An evaluation result MUST be distinguishable from the absence of an
  evaluation — a query for a call with no evaluation yet MUST NOT return a result that
  could be mistaken for a passing or zero score.
- **FR-009**: This feature's resources MUST be deployable, verifiable, and destroyable
  independently of `infra/main.bicep`'s resource group, so that one can be torn down
  without affecting the other.
- **FR-010**: Every resource type this feature proposes to create MUST be checked against
  "does it bill while idle" before it is created, with the answer, the daily rate if
  nonzero, and the deletion command recorded in this spec's Cost section — satisfied
  above.
- **FR-011**: No deployment or evaluation run against the live subscription may happen
  without an explicit action taken by the author in the session it happens; nothing in
  this feature runs unattended or on a schedule.
- **FR-012**: A read-only dry run (`az deployment group what-if` or equivalent) MUST be
  reviewed against the live subscription before the redeployment of
  `infra/foundry.bicep`, consistent with constitution Principle V.

### Key Entities

- **Foundry account, Foundry project, model deployment**: as defined in spec 006 — the
  redeployed target this feature's calls and evaluations run against.
- **Evaluation result**: a retrievable record linking a specific call (via its trace,
  per spec 006) to a quality judgment — at minimum a metric name, a score or verdict, and
  the prompt version and call it evaluated.
- **Groundedness verdict**: a specific kind of evaluation result whose judgment concerns
  whether a response's claims are supported by stated source material, distinct from a
  general quality score.
- **Prompt variant comparison**: a pairing of two evaluation results, each attributed to
  a different committed revision of the same prompt file, answering the same test
  question.
- **Invocation**: any model call this feature's verification makes, whether it is a call
  being evaluated or a judge call made to produce an evaluation — the unit SC-006's cap
  is counted in.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `az cognitiveservices account deployment show` (or equivalent) read against
  the redeployed model deployment reports a SKU name of `Standard` or `GlobalStandard`.
- **SC-002**: For at least one call, a query run in a session separate from the one that
  made the call returns both the call's trace (per spec 006's SC-004) and an evaluation
  result attributed to it, naming the metric and the score or verdict.
- **SC-003**: A groundedness check run against a response with an unsupported claim
  records a failing verdict, and the same check run against a fully supported response
  records a passing verdict — both retrievable and distinguishable from each other.
- **SC-004**: Evaluation results for two committed prompt revisions answering the same
  test question are retrieved together, and which revision scored higher is stated
  directly by the query output, not left to be computed by the reader.
- **SC-005**: `git log --follow` (or equivalent) on the prompt file(s) used for this
  feature's comparison shows at least two revisions, confirming the comparison in SC-004
  used tracked, diffable prompt versions rather than untracked strings.
- **SC-006**: The total number of model invocations made during this feature's
  verification — calls being evaluated plus any judge calls — does not exceed **500**,
  confirmed by a count derived from the trace/evaluation records themselves (not from a
  running tally kept outside the system), before the verification is reported complete.
- **SC-007**: `az group delete --name <this feature's resource group> --yes`, followed by
  `az resource list` scoped to that group, leaves zero resources — confirming the whole
  feature is removable in one command with nothing left behind.
- **SC-008**: The measured at-rest daily cost of this feature's resource group, read from
  Cost Management after data is available (not assumed on the day of deployment — see
  Edge Cases), is **€0.00** for any day with zero completion or evaluation requests sent.

### Deferred Criteria

Declared here rather than discovered at closing time — the pattern spec 006 established
after feature 005 closed with a criterion it could not read on the day it was scheduled
(Cost Management data lags ingestion by roughly 8–24 hours, per `infra/DEPLOY.md` § 4).

| Criterion | Depends on | Readable from |
| --- | --- | --- |
| SC-008 — measured at-rest cost | Cost Management data for the deployment day | the day after deployment |

## Assumptions

- **A new, dedicated resource group hosts this feature**, matching block 3's pattern
  (Assumptions, spec 006) rather than reusing `rg-ai300-foundry`'s exact name if that
  name is still locked by a soft-deleted dependency — its exact name is a plan-level
  detail, resolved when `infra/foundry.bicep` is redeployed (FR-001).
- **The evaluation mechanism (rubric-based scoring, LLM-as-judge, or a programmatic
  groundedness check) is a plan-level choice.** This spec requires only that evaluation
  results exist, are retrievable, distinguish pass/fail or score meaningfully, and stay
  within SC-006's invocation cap — not which technique produces them.
- **The trace store from block 3 (Log Analytics + Application Insights) is reused rather
  than replaced.** Evaluation results are additional attributes or spans linked to the
  same call records, not a second, parallel storage mechanism — consistent with FR-004's
  requirement to reuse `prompt.version` rather than invent a parallel identifier.
- **This feature is deployed by the author running `az deployment group create` directly,
  not through the existing GitHub Actions pipeline**, for the same reason spec 006 gave:
  routing an exploratory, differently-regioned feature through the CI role would widen
  its blast radius to a second resource group for infrastructure meant to be small and
  disposable.
- **The specific model deployed is chosen at implementation time** from whatever
  `az cognitiveservices model list -l swedencentral` reports as token-billed at that
  moment, not fixed here — this spec's Cost section uses `gpt-5-nano`'s published rate
  only to size the invocation budget.
- **The 500-invocation ceiling in SC-006 is sized for this feature's verification, not
  for ongoing use.** It comfortably covers a small comparison matrix (a handful of test
  questions × two or three prompt revisions × one or two metrics, including judge calls)
  while remaining an order of magnitude below a volume that would meaningfully change
  this feature's cost profile.
