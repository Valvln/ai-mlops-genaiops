---

description: "Task list for Block 3 — Azure AI Foundry GenAIOps backbone"
---

# Tasks: Block 3 — Azure AI Foundry GenAIOps backbone

**Input**: Design documents from `/specs/006-foundry-genaiops/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Not included as a separate suite. This feature's verification is
observation-by-query (send a call, then retrieve its record in a separate
step) — the same pattern feature 005 used. Each user story phase below ends
with the observation that proves it, in place of a test task.

**Organization**: Tasks are grouped by user story (P1 → P2 → P2, matching
spec.md) so each can be implemented, deployed, and verified independently.

## Path Conventions

Per [plan.md](./plan.md)'s Project Structure: `infra/foundry.bicep` (new,
sibling of `main.bicep`, never merged into it) and
`genaiops/foundry-block3/` (new workload folder).

---

## Phase 1: Setup

**Purpose**: Live prerequisites and repository scaffolding — nothing Azure-side
is created here beyond the resource group.

- [X] T001 Create the resource group: `az group create --name rg-ai300-foundry --location swedencentral --tags project=ai300-prep environment=learning` (research.md § R5)
- [X] T002 [P] Re-verify `gpt-4.1-mini` availability and quota in `swedencentral` — `az cognitiveservices model list -l swedencentral` and `az cognitiveservices usage list -l swedencentral`, confirm `GlobalStandard` SKU and nonzero limit before writing it into the template (FR-004, research.md § R4's re-verification instruction — a model can go from available to deprecated, or from quota to zero, between this plan and implementation)
- [X] T003 [P] Scaffold `genaiops/foundry-block3/pyproject.toml` with `uv`, pinning `openai`, `azure-identity`, `prompty`, `opentelemetry-sdk`, `azure-core-tracing-opentelemetry` (plan.md Technical Context)

**Checkpoint**: Resource group exists; the model choice is reconfirmed live, not trusted from research.md's 2026-08-19 snapshot; the local environment is ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared Azure anchor every user story attaches to — the
Foundry account and project. No user story's Azure-side work can start before
this exists.

**⚠️ CRITICAL**: Complete this phase before starting Phase 3, 4, or 5's Azure-touching tasks.

- [X] T004 Create `infra/foundry.bicep` declaring the Foundry account (`Microsoft.CognitiveServices/accounts`, kind `AIServices`, sku `S0`, `location: 'swedencentral'`) and the Foundry project (`accounts/projects`) per [data-model.md](./data-model.md)'s Infrastructure entities table and [contracts/foundry-deployment.md](./contracts/foundry-deployment.md)
- [X] T005 `az bicep build --file infra/foundry.bicep` — confirm exit 0 and no output (constitution Principle V)
- [X] T006 `az deployment group what-if --resource-group rg-ai300-foundry --template-file infra/foundry.bicep` — review against [contracts/foundry-deployment.md](./contracts/foundry-deployment.md)'s expected creates (account + project only, at this point) before deploying (FR-011)
- [X] T007 `az deployment group create` to deploy the account and project, author-approved (FR-010)

**Checkpoint**: Foundry account and project exist in `rg-ai300-foundry`. User story work can begin.

---

## Phase 3: User Story 1 - A token-billed model answers a call (Priority: P1) 🎯 MVP

**Goal**: One `GlobalStandard` model deployment exists and answers a real
request, provably never billed by the hour.

**Independent Test**: Deploy the model, send one request, read back the
response and the deployment's own SKU. No prompt file and no trace query need
exist yet.

### Implementation for User Story 1

- [X] T008 [US1] Extend `infra/foundry.bicep` with the model deployment (`accounts/deployments`, sku `GlobalStandard`, capacity `1`, model `{format: OpenAI, name: gpt-4.1-mini, version: 2025-04-14}`) per research.md § R4
- [X] T009 [US1] `az bicep build` + `az deployment group what-if` + `az deployment group create` to add the deployment to the existing account (contracts/foundry-deployment.md pre/post-deployment checks)
- [X] T010 [US1] Verify the deployment's SKU by reading the service — `az cognitiveservices account deployment show -n <account> -g rg-ai300-foundry --deployment-name gpt-4.1-mini --query sku.name` — confirm `GlobalStandard`, never a PTU-family SKU (SC-001, User Story 1 Acceptance Scenario 1)
- [X] T011 [US1] Write `genaiops/foundry-block3/call_model.py`: authenticate with `azure-identity`, send one completion request to the `gpt-4.1-mini` deployment using a simple inline test prompt, print the response (contracts/call-and-trace.md § `call_model.py`)
- [X] T012 [US1] Run `call_model.py` once; confirm a successful response is returned and attributable to token usage, not a standing charge (SC-002, User Story 1 Acceptance Scenarios 2–3)
- [X] T012a [US1] **Not planned — added from a refusal.** T012's first run returned `401 PermissionDenied` naming the missing data action `Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action`: Owner is a control-plane role and grants nothing on the Cognitive Services data plane. Declare a `Cognitive Services OpenAI User` assignment for the caller in `infra/foundry.bicep`, scoped to the account, behind a `callerPrincipalId` parameter — in the template rather than a one-off `az role assignment create`, so it survives the destroy/rebuild cycle this resource group is designed for. The CI role in `infra/ci-identity.bicep` is untouched (FR-012 stays dormant)

**Checkpoint**: User Story 1 is independently functional — deployed, callable, and provably token-billed. This is the MVP.

---

## Phase 4: User Story 2 - The prompt behind a call is a versioned file (Priority: P2)

**Goal**: The prompt used to exercise the model lives in the repository as a
file with real git history, not typed once into the Foundry portal.

**Independent Test**: Edit the prompt file, commit, confirm its git history
shows more than one revision — independent of whether any trace has been
queried.

### Implementation for User Story 2

- [X] T013 [P] [US2] Create `genaiops/foundry-block3/prompts/hello-domain3.prompty` with YAML frontmatter (model config) and a prompt body (research.md § R7)
- [X] T014 [US2] Commit the prompt file, then edit it and commit again, so real git history exists before it's used for verification (FR-006)
- [X] T015 [US2] Modify `call_model.py` (from US1) to accept a `.prompty` file path argument and load the prompt from it, replacing the T011 inline test prompt (contracts/call-and-trace.md — integrates with User Story 1)
- [X] T016 [US2] Verify: `git log --follow --oneline -- genaiops/foundry-block3/prompts/hello-domain3.prompty` shows ≥2 revisions (SC-003, User Story 2 Acceptance Scenario 2)

**Checkpoint**: User Stories 1 and 2 both work — the model answers a call made with a prompt that has real, diffable git history.

---

## Phase 5: User Story 3 - A past call can be traced without having watched it happen (Priority: P2)

**Goal**: A call can be made, the terminal closed, and its record — prompt
version, deployment identity, response — retrieved later by a separate query.

**Independent Test**: Make one call, close the terminal that made it, retrieve
its record through a separate invocation.

### Implementation for User Story 3

- [X] T017 [US3] Extend `infra/foundry.bicep` with a Log Analytics workspace (`Microsoft.OperationalInsights/workspaces`) and a workspace-based Application Insights resource (`Microsoft.Insights/components`) per [data-model.md](./data-model.md)
- [X] T018 [US3] Extend `infra/foundry.bicep` with the account-level and project-level connections (`accounts/connections`, `accounts/projects/connections`, category `AppInsights`) targeting the Application Insights resource — **validate `api-version 2025-04-01-preview` with `az bicep build` + `what-if` before deploying**; this is research.md § R3/R6's explicitly-flagged, not-yet-what-if'd item, sourced from a public sample, not the live subscription
- [X] T019 [US3] Deploy the updated template; verify exactly the 7 resources in [contracts/foundry-deployment.md](./contracts/foundry-deployment.md) exist — `az resource list -g rg-ai300-foundry --query "[].type"` (SC-005)
- [X] T020 [US3] ~~Grant the querying identity the **Log Analytics Reader** role~~ — **verified unnecessary, no grant made.** research.md § R6 cited this as a likely requirement and contracts/call-and-trace.md hedged it as "may need an explicit role assignment". It does not: `query_trace.py` retrieved the record on its first attempt as subscription Owner. Log Analytics query is authorised by the control-plane action `Microsoft.OperationalInsights/workspaces/query/read`, which Owner's `*` covers — unlike Cognitive Services inference (T012a) and Foundry connection reads (T021a), which are **data** actions Owner does not reach. The lesson is not "Owner is enough" but "control-plane and data-plane are different systems, and which one guards a given API has to be read, not guessed". No role assignment is declared for this, because granting a permission that was never refused is how a least-privilege posture quietly stops meaning anything
- [X] T021a [US3] **Not planned — added from a refusal, and it changed a design decision.** The intended way to configure tracing was to let the app discover its own telemetry target through the project connection (`AIProjectClient.telemetry.get_application_insights_connection_string()`). Refused: `PermissionDenied — lacks the required data action Microsoft.CognitiveServices/accounts/AIServices/connections/read`. Closing it would cost more than it buys — the only built-in role carrying that action is `Cognitive Services User` (dataActions `Microsoft.CognitiveServices/*`, the whole data plane, for one lookup), and a one-action custom role is an authorization-provider object that survives `az group delete` and would leave exactly the residue SC-007 asserts is absent. `call_model.py` therefore takes the connection string from the App Insights resource, `azure-ai-projects` was removed from the dependency list, and the two connections remain what they are: the wiring the portal reads, deployed and verified by listing them through the ARM connections API
- [X] T021 [US3] Instrument `call_model.py` with OpenTelemetry (`opentelemetry-sdk`, `azure-core-tracing-opentelemetry`): resolve the prompt file's current git commit hash and attach it as a span attribute **before** sending the call, export the span to the connected Application Insights resource (contracts/call-and-trace.md § `call_model.py`)
- [X] T022 [US3] Write `genaiops/foundry-block3/query_trace.py`: query the Log Analytics workspace for a given trace id or time range, print the prompt version, deployment name, and response content read back from the record — never from in-memory state (contracts/call-and-trace.md § `query_trace.py`)
- [X] T023 [US3] Verify retrieval end-to-end: run `call_model.py`, then — in a separate invocation, ideally a new terminal — run `query_trace.py`; confirm it returns the correct prompt version, deployment, and response (SC-004, User Story 3 Acceptance Scenario 1)
- [X] T024 [US3] Verify distinguishability: run `call_model.py` twice against two different prompt revisions (from US2's git history), then `query_trace.py` for both; confirm the two records are distinguishable by prompt version, not merely by timestamp (SC-004 extended, User Story 3 Acceptance Scenario 2)

- [X] T024a [US3] **Not planned — a real defect, found because T024 asked for two records and got one.** The first `call_model.py` ended after its span closed and let the OpenTelemetry batch processor ship whatever it had at interpreter exit. Of two calls, one arrived; three hours later the workspace still held exactly one `genaiops.call` record, so this was a loss and not ingestion lag. A span queued in a batch processor is not a span that was exported, and a short-lived CLI process is where that gap opens — the process is gone long before the next scheduled export. `call_model.py` now calls `force_flush()` and warns if it returns false. Worth noting how close this came to passing unnoticed: T023 had already retrieved a trace successfully, so the tracing looked proven. It took a criterion that demanded **two** records to expose that the mechanism was unreliable rather than working

**Checkpoint**: All three user stories are independently functional. The block's Domain 3 trio — model, versioned prompt, traced call — is demonstrable end to end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and the criteria that only make sense once everything above exists.

- [X] T025 [P] Draft `genaiops/foundry-block3/README.md` — what was built and the observed values, in the first person, for the author's review (constitution Principle IV; Claude drafts, the author edits and commits)
- [X] T026 Run [quickstart.md](./quickstart.md) end to end as a final check, from pre-flight through teardown, on a session separate from the one that built each piece — steps 1 and 3–5 re-run verbatim against the corrected document; step 2's deployment had already run in the same form, steps 6–7 are T027 and T028 below

**T027 and T028 cannot both be satisfied on the deployment day, and the
conflict is in the criteria rather than in the work.** SC-006 asks for the
measured cost of **a day with zero completion requests**; 2026-08-19 had six.
Tearing down on the deployment day would mean no such day ever exists, leaving
the spec's one cost criterion permanently unmeasurable.

Decided by the author on 2026-08-19: **leave the resource group standing
overnight, make no further calls, and close both criteria on 2026-08-20.**
What that costs was checked rather than assumed — the Retail Prices API
publishes no per-hour or per-instance meter for any of the four resource types
in `swedencentral`, which is the very claim SC-006 exists to verify by
measurement. The standing "never leave anything running" rule is a cost rule,
and there is no compute here and no hourly meter; an idle day is the
observation, not a lapse.

**Attempted on 2026-08-20. The day with calls is measured; the idle day is not
yet readable — and establishing that second half took a measurement of its
own.** Cost Management, scoped to `rg-ai300-foundry`, daily granularity,
grouped by service and meter, returns for 2026-08-19:

| Meter | EUR |
| --- | --- |
| Foundry Models — `gpt 4.1 mini Inp glbl Tokens` | 0.000440 |
| Foundry Models — `gpt 4.1 mini Outp glbl Tokens` | 0.000599 |
| Log Analytics — `Analytics Logs Data Ingestion` | 0.000000 |
| **Total** | **0.001039** |

Six completion requests cost a tenth of a cent, and every line of it is either
a per-token meter or a free-tier ingestion. No hourly, per-instance or standing
charge appears for any of the four resource types — the claim SC-006 exists to
verify, until now supported only by the Retail Prices API's silence and now
readable on a bill.

For 2026-08-20 the same query returns no rows — and returns none **for the
entire subscription**, not only for this resource group. The control is
`rg-ai300-test02`, which stands with seven resources and billed €0.098867 on
2026-08-18 and €0.146405 on 2026-08-19, one row per day without a gap. Its
2026-08-20 row is missing too, so nothing has landed for that day at all: this
is `infra/DEPLOY.md` § 4's 8–24h lag, not a zero. Recorded as **data not
available**, which is what makes it a deferral rather than the confirmed-zero
mistake that caution was written about.

A second obstacle is independent of the lag: the query ran at 08:32 CEST, when
the idle day was eight hours old. Even once its rows land, that is a partial
day, not "a day with zero completion requests".

Decided by the author on 2026-08-20: **let the resource group stand through the
whole of 2026-08-20 with no calls, read the complete idle day on 2026-08-21,
and tear down after.** What the extra day can cost is bounded by the table
above rather than assumed: with no calls the two token meters have nothing to
meter, and the only other line was already €0.00.

- [ ] T027 SC-006 — **half measured**. 2026-08-19, the day with six calls, reads €0.001039 with the per-meter breakdown above. The idle-day reading waits for 2026-08-20's rows to land, i.e. 2026-08-21; the absent row was recorded as unavailable and retried, never treated as a zero
- [ ] T028 SC-007, **after T027**: `az group delete --name rg-ai300-foundry --yes`, then `az resource list -g rg-ai300-foundry` confirms zero resources remain. Ordered after T027 because the teardown destroys the subject of the measurement. Pre-teardown baseline read 2026-08-20, so that "nothing left behind" is a comparison and not an impression: four resources (account, project, Log Analytics workspace, Application Insights component), zero role assignments at the resource group scope, and no custom role definition belonging to this feature — the subscription's only one, `AI300 CI Deployer (rg-ai300-test02)`, is feature 003's. Both system-assigned identities, the account's `7f01355b-d9df-47d9-8c55-b1eff5c1187e` and the project's `3d72fddd-c5f6-4913-bbf5-10a00c20a07b`, hold no assignment at any scope. The role **definition** list is the one to re-read afterwards, but not for the reason written here first: this task claimed definitions outlive the resource group they were scoped to, and that is wrong. Tearing down `rg-ai300-test02` on 2026-08-20 took `AI300 CI Deployer (rg-ai300-test02)` with it — `az role definition list --custom-role-only true` returned empty, and a direct lookup of the definition id answered `RoleDefinitionDoesNotExist`, so it is a deletion and not a listing artefact. A definition whose only `assignableScopes` entry is a deleted group does not survive it, as `infra/DEPLOY.md` § 6.2 already recorded. That also retires the baseline above: the subscription now holds no custom role definition at all, so an empty list after this teardown proves nothing about feature 006 by itself

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately (T002, T003 parallelizable with each other; T001 independent of both)
- **Foundational (Phase 2)**: Depends on T001 (resource group must exist) — BLOCKS all user stories' Azure-side work
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2). No dependency on US2 or US3
- **User Story 2 (Phase 4)**: T013 has no dependency and can start as soon as Setup is done (a `.prompty` file needs no Azure resource). T015 depends on T011 (US1's `call_model.py` must exist to be modified) — this is the one deliberate cross-story integration point, consistent with spec's Assumption that US2 "may integrate with US1"
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) for T017–T019, on User Story 1 (T011) for T021 (there is no `call_model.py` to instrument otherwise), and on User Story 2 (T013) for the prompt-version attribute T021 attaches
- **Polish (Phase 6)**: Depends on whichever stories are in scope for a given delivery; T027 and T028 depend on Phase 2's deployment existing at all

### User Story Dependencies

- **User Story 1 (P1)**: Independent after Foundational — the MVP
- **User Story 2 (P2)**: Independent for its own acceptance test (T013, T014, T016 need nothing from US1); T015's integration is a convenience, not a hard requirement — the prompt file and its git history are provable without a single call ever being made
- **User Story 3 (P2)**: The one story that is not fully independent — tracing a call requires a call to exist (US1) and benefits from a versioned prompt to attribute (US2). This is stated as a dependency in spec.md itself ("Depends on User Story 1... and benefits from User Story 2"), not a violation of story independence

### Within Each User Story

- Infrastructure (Bicep extension) before the script that calls it
- `az bicep build` before `what-if` before `az deployment group create` — never skip a step (constitution Principle V)
- Verification task last, reading from the live service, never from what was requested

### Parallel Opportunities

- T002 and T003 (Setup) — different concerns, no shared file
- T013 (US2's prompt file) can be authored any time after Setup, in parallel with Phase 2/3's Azure work — it touches no Azure resource and no shared file
- T025 (README draft) can start once enough of Phases 3–5 exist to describe, in parallel with T026–T028

---

## Parallel Example: Setup and User Story 2's prompt file

```bash
# Setup, run together:
Task: "Re-verify gpt-4.1-mini quota in swedencentral"
Task: "Scaffold genaiops/foundry-block3/pyproject.toml"

# Once Setup is done, US2's prompt file needs nothing from Phase 2/3 and can
# be drafted while the Foundry account/project/deployment are being deployed:
Task: "Create genaiops/foundry-block3/prompts/hello-domain3.prompty"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (account + project)
3. Complete Phase 3: User Story 1 — a model deployment that answers a call
4. **STOP and VALIDATE**: T010 and T012 independently prove the MVP
5. This is already a demonstrable Domain 3 artifact — a token-billed
   deployment — before either P2 story exists

### Incremental Delivery

1. Setup + Foundational → shared Azure anchor ready
2. User Story 1 → MVP: deployed, callable, provably token-billed
3. User Story 2 → the prompt becomes a versioned file; `call_model.py` reads
   it instead of an inline string
4. User Story 3 → tracing infrastructure, instrumentation, and retrieval —
   the block's observability objective, closing last because it is the one
   story that genuinely needs the other two to exist first

### Solo Session Strategy

This is a one-author, one-session-at-a-time project (constitution Principle
III — every commit is reviewed and authorized in session). The phase order
above doubles as the commit order: each checkpoint is a natural "propose a
commit here" boundary, one logical change at a time, matching how features
004 and 005 were built.

---

## Notes

- `[P]` tasks touch different files with no dependency on an incomplete task
- `[Story]` labels map every Phase 3+ task to spec.md's US1/US2/US3
- Every Azure-touching task follows build → what-if → deploy → verify against
  the live service, never against what was requested (the repository's
  recurring lesson — `infra/DEPLOY.md`'s "read the captured error, not the
  green summary")
- Stop at any checkpoint to validate a story independently before continuing
- T018 carries this plan's one remaining unverified assumption (the
  `connections` resource API version) — resolve it with `what-if`, not by
  trusting the cited sample, before proposing that part of the template for
  deployment
