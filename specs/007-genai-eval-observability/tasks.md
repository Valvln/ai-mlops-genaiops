---

description: "Task list for Block 4 — GenAI QA and Observability"
---

# Tasks: Block 4 — GenAI QA and Observability

**Input**: Design documents from `/specs/007-genai-eval-observability/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Not included as a separate suite. This feature's verification is
observation-by-query, extending block 3's own pattern one layer up: score a
call, then retrieve the score in a separate invocation. Each user story phase
below ends with the observation that proves it, in place of a test task.

**Organization**: Tasks are grouped by user story (P1 → P2 → P2, matching
spec.md) so each can be implemented and verified independently.

## Path Conventions

Per [plan.md](./plan.md)'s Project Structure: `infra/foundry.bicep` is
redeployed unchanged (no edits); all new code lives in
`qa-observability/foundry-block4/`, a sibling of `genaiops/foundry-block3/`
which is read from but not written to.

---

## Phase 1: Setup

**Purpose**: Clear the way for the redeploy and scaffold the local
environment — nothing Azure-side beyond the resource group and the pre-flight
check is created here.

- [X] T001 Check for the soft-deleted Foundry account from feature 006's
  teardown — `az cognitiveservices account list-deleted -o table` — and if
  `ai300fdrylkcq74thutjeq` (`swedencentral`) is still held, purge it:
  `az cognitiveservices account purge -g rg-ai300-foundry -n
  ai300fdrylkcq74thutjeq -l swedencentral` (research.md § R1,
  contracts/foundry-redeployment.md step 1 — a mutating call, run as an
  explicit, author-authorized action)
- [X] T002 [P] Create the resource group: `az group create --name
  rg-ai300-foundry --location swedencentral --tags project=ai300-prep
  environment=learning` (contracts/foundry-redeployment.md step 2)
- [X] T003 [P] Scaffold `qa-observability/foundry-block4/pyproject.toml` with
  `uv`, pinning `azure-ai-evaluation>=1.18,<2` alongside `openai`,
  `azure-identity`, `opentelemetry-sdk`, `azure-core-tracing-opentelemetry`
  (plan.md Technical Context, research.md package pin)

**Checkpoint**: The redeploy target's name is free to reuse; the resource
group exists; the local environment is ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Redeploy the shared Azure anchor every user story attaches to —
identical to feature 006's, not modified. No user story's Azure-side work can
start before this exists.

**⚠️ CRITICAL**: Complete this phase before starting Phase 3, 4, or 5's Azure-touching tasks.

- [X] T004 `az bicep build --file infra/foundry.bicep` — confirm exit 0 and no
  output; the file is unchanged from feature 006, so this is expected to pass
  trivially, and a failure here would itself be a finding, not something to
  route around (contracts/foundry-redeployment.md step 3)
- [X] T005 Re-verify `gpt-4.1-mini` `GlobalStandard` quota in `swedencentral`
  — `az cognitiveservices usage list -l swedencentral --query
  "[?name.value=='OpenAI.GlobalStandard.gpt4.1-mini']"` (mind the meter's own
  spelling, no hyphen before `4.1`) — confirm nonzero before deploying, per
  feature 006's own R4 re-verification instruction (contracts/foundry-redeployment.md
  step 5)
- [X] T006 `az deployment group what-if --resource-group rg-ai300-foundry
  --template-file infra/foundry.bicep` — review against feature 006's own
  recorded shape (account, project, deployment, Log Analytics + App Insights
  pair, two connections, one role assignment) before deploying (constitution
  Principle V, contracts/foundry-redeployment.md step 4)
- [X] T007 `az deployment group create --resource-group rg-ai300-foundry
  --template-file infra/foundry.bicep --parameters
  callerPrincipalId=<author's object id>`, author-approved
  (contracts/foundry-redeployment.md step 6)
- [X] T008 Verify the redeployment matches the contract: `az
  cognitiveservices account deployment show` reports SKU `GlobalStandard`
  (SC-001) and `az resource list -g rg-ai300-foundry --query "[].type"`
  reports the same four resource types feature 006's own T028 baseline
  recorded — the concrete form of this feature's "redeployment is itself
  proof" claim (contracts/foundry-redeployment.md steps 7–8)

**Checkpoint**: The Foundry account, project, deployment, and trace store
exist in `rg-ai300-foundry`, verified identical in shape to feature 006's.
User story work can begin.

---

## Phase 3: User Story 1 - A response gets a quality score attached to its trace (Priority: P1) 🎯 MVP

**Goal**: A call's response is scored by an evaluator, and the result is
retrievable afterward, joined to the call it scored.

**Independent Test**: Send one call, run one evaluation against its response,
confirm the result is retrievable by a query naming that specific call.

### Implementation for User Story 1

- [X] T009 [US1] Write `qa-observability/foundry-block4/evaluate_call.py`,
  `--trace-id` path: query the Log Analytics workspace for the named
  trace's `prompt.file`, `prompt.version`, `gen_ai.request.model`, and
  `gen_ai.response.content` (reusing the query block 3's `query_trace.py`
  already runs); build `AzureOpenAIModelConfiguration` with no `api_key`
  (Entra ID via `DefaultAzureCredential`); run the evaluator named by
  `--metric` (`groundedness` or `relevance`) against `gpt-4.1-mini` as judge;
  emit a `genaiops.eval` span with the attributes in
  [data-model.md](./data-model.md)'s Evaluation record table, set before/after
  the evaluator call per [contracts/evaluate-and-retrieve.md](./contracts/evaluate-and-retrieve.md);
  `force_flush()` before exit
- [X] T010 [US1] Write `qa-observability/foundry-block4/query_evaluations.py`,
  `--trace-id` mode: query `genaiops.eval` spans, join by
  `eval.evaluated_trace_id` to the corresponding `genaiops.call` record, print
  the prompt version, deployment identity, and score together; if no
  `genaiops.eval` span names the requested trace id, print that in words, never
  a row standing in for a zero score (contracts/evaluate-and-retrieve.md, FR-008)
- [X] T011 [US1] Run `call_model.py` (unchanged, from
  `genaiops/foundry-block3/`) once against `hello-domain3.prompty`, producing
  one call and its trace id
- [X] T012 [US1] Run `evaluate_call.py --trace-id <id> --metric relevance`
  against T011's call; confirm `eval.score` and `eval.result` are set (SC-002,
  User Story 1 Acceptance Scenario 1)
- [X] T013 [US1] In a separate invocation, run `query_evaluations.py
  --trace-id <id>`; confirm it returns the joined record — prompt version,
  deployment, score — read from the trace store, not from anything printed
  earlier (SC-002, User Story 1 Acceptance Scenario 2)
- [X] T014 [US1] Verify FR-008: run `query_evaluations.py --trace-id` against
  a call that was deliberately never scored; confirm the output states the
  absence in words, distinguishable from a passing or zero score (User Story 1
  Acceptance Scenario 3)

**Checkpoint**: User Story 1 is independently functional — a scored call,
retrievable after the fact. This is the MVP.

---

## Phase 4: User Story 2 - Two prompt variants are compared on the same metric (Priority: P2)

**Goal**: Two committed revisions of the same prompt file are evaluated on the
same question, and the comparison states which revision scored higher.

**Independent Test**: Evaluate the same test question against two committed
prompt revisions; confirm the two results are retrievable side by side,
attributed to their own revision.

### Implementation for User Story 2

- [X] T015 [P] [US2] Create
  `qa-observability/foundry-block4/prompts/grounded-qa.prompty`, revision 1: a
  bare instruction ("answer the question") with a `context` input field
  (research.md § R8)
- [X] T016 [US2] Commit revision 1, then edit `grounded-qa.prompty` to a
  context-constrained instruction ("answer only from the material given; say
  so if it isn't covered") and commit again, so ≥2 revisions exist before
  verification (FR-006)
- [X] T017 [US2] Run `call_model.py` (from `genaiops/foundry-block3/`,
  pointed at `grounded-qa.prompty`) once per revision, producing two calls and
  two trace ids
- [ ] T018 [US2] Run `evaluate_call.py --trace-id` for each of T017's two
  calls, same `--metric groundedness`, producing two `genaiops.eval` records
- [X] T019 [US2] Extend `query_evaluations.py` with `--compare <version-a>
  <version-b> --metric <name>`: retrieve both revisions' records for the named
  metric and state directly which `prompt.version` scored higher
  (contracts/evaluate-and-retrieve.md, SC-004)
- [ ] T020 [US2] Verify: `git log --follow --oneline --
  qa-observability/foundry-block4/prompts/grounded-qa.prompty` shows ≥2
  revisions (SC-005), and `query_evaluations.py --compare` states the
  direction of the difference, not two bare numbers (SC-004)

**Checkpoint**: User Stories 1 and 2 both work — a scored call, and a
comparison across prompt revisions with a stated direction.

---

## Phase 5: User Story 3 - A response is checked for groundedness against its source (Priority: P2)

**Goal**: A grounded response passes the groundedness check; a response with
an unsupported claim fails it — both retrievable and distinguishable.

**Independent Test**: Evaluate one response known to contain an unsupported
claim and confirm it's flagged; evaluate one fully supported response and
confirm it isn't.

### Implementation for User Story 3

- [X] T021 [P] [US3] Author
  `qa-observability/foundry-block4/fixtures/unsupported_claim.json` — a
  hand-written `query`/`context`/`response` triple where `response` asserts
  something `context` does not support (research.md § R7)
- [X] T022 [US3] Extend `evaluate_call.py` with the `--fixture <path>` path:
  load the JSON file directly (no Azure query needed to resolve the input),
  set `eval.evaluated_trace_id` to the literal `"fixture"`
  (contracts/evaluate-and-retrieve.md § `evaluate_call.py`)
- [X] T023 [US3] Run `evaluate_call.py --trace-id <a call from T011 or T017>
  --metric groundedness`; confirm `eval.result` reads `pass` (User Story 3
  Acceptance Scenario 1)
- [X] T024 [US3] Run `evaluate_call.py --fixture
  fixtures/unsupported_claim.json --metric groundedness`; confirm
  `eval.result` reads `fail` (User Story 3 Acceptance Scenario 2)
- [ ] T025 [US3] Verify both are retrievable and distinguishable:
  `query_evaluations.py --trace-id <the real trace id>` and
  `query_evaluations.py --trace-id fixture` (SC-003)

**Checkpoint**: All three user stories are independently functional. The
block's Domain 4 trio — a scored call, a prompt comparison, a groundedness
check — is demonstrable end to end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and the criteria that only make sense once
everything above exists.

- [X] T026 [P] Draft `qa-observability/foundry-block4/README.md` — what was
  built and the observed values, in the first person, for the author's review
  (constitution Principle IV; Claude drafts, the author edits and commits)
- [X] T027 Extend `query_evaluations.py` with `--count-invocations --since
  <window>`: sum `genaiops.call` and `genaiops.eval` spans in the window
  directly from the trace store — never a side tally — and confirm the
  feature's total verification stayed well under SC-006's 500-invocation
  ceiling (contracts/evaluate-and-retrieve.md's accounting rule)
- [ ] T028 Run [quickstart.md](./quickstart.md) end to end as a final check,
  from pre-flight through teardown, on a session separate from the one that
  built each piece
- [ ] T029 SC-008, deferred per spec.md's Deferred Criteria table: the day
  after deployment, read Cost Management for a day with zero calls sent —
  confirm €0.00, reading an absent row as "no data yet" and checking against a
  control resource group known to be billing the same day, never assuming a
  missing row is a confirmed zero (spec.md Edge Cases, `infra/DEPLOY.md` § 4)
- [X] T030 SC-007, after T029: `az group delete --name rg-ai300-foundry
  --yes`, then `az resource list -g rg-ai300-foundry` confirms zero resources
  remain. Also record `az cognitiveservices account list-deleted`'s new entry
  and its `scheduledPurgeDate` — the exact fact this feature's own R1 needed
  from feature 006, so whatever reuses this resource group next doesn't have
  to rediscover it

---

## Phase 7: Findings from the first real run

**Purpose**: Close what building this feature disproved. Added 2026-08-23,
after the redeploy-and-evaluate session; each task cites its entry in
[findings.md](./findings.md), where the measurement behind it is recorded.

**⚠️ T031 blocks the feature's own central claim.** SC-002 says an evaluation
is retrievable after the fact. Right now some are and some are not, so T013,
T014, T020 and T025 cannot be honestly verified until this is resolved.

- [ ] T031 Resolve F6 — `genaiops.eval` spans are missing from Log Analytics
  while `force_flush()` reports success. First, the free half of the
  experiment: re-query the workspace hours after the fact and see whether the
  missing spans appeared, which separates unexpected ingestion lag from real
  loss. If they are genuinely lost, print the tracer provider's identity before
  and after the evaluator call in
  `qa-observability/foundry-block4/evaluate_call.py` — the leading hypothesis
  is that `azure-ai-evaluation`'s bundled promptflow tracing replaces the
  global provider, so the flush drains a provider that never held the span
- [X] T032 Fix F1 and F2 in `infra/foundry.bicep` — add the `dependsOn` that
  serializes `accounts/projects` against `accounts/connections`, and make the
  connections re-deployable or drop them, having first asked whether they earn
  their place at all (nothing in this repository reads them). Validate with
  `az bicep build`, then prove it by deploying twice into an empty resource
  group: the second run must succeed, which is the property F2 says the
  template does not currently have
- [X] T033 Fix F3 in `infra/foundry.bicep` — set the model deployment's
  `capacity` to 10 so the template matches the live resource this session
  changed by hand. Free on a token-billed SKU (capacity is a throttle, not a
  reservation), and until it lands the template and reality disagree
- [ ] T034 After T032 and T033, record F1–F3 in `infra/DEPLOY.md` — a
  template that cannot be re-run and a capacity that throttles to one request
  per minute are exactly the "easiest to walk into" class that runbook exists
  for. Note that touching `infra/**` arms the CI deploy gate

---

## Where this stands, 2026-08-23

**Done and verified**: the redeploy (on a template this block had to fix
first), User Story 1 end to end including FR-008's absence case, both
directions of the groundedness check at evaluation time, the invocation count,
and teardown — verified clean, with the resource group gone, no soft-deleted
account, the workspace genuinely deleted and the quota released.

**Left open, all for the same reason.** F6: roughly 70% of spans never reach
the workspace, though the exporter is acknowledged with `HTTP 200` and
`Items accepted`. Everything below needs a *particular* record to survive that:

| Task | What it needs |
| --- | --- |
| T018, T020 | Two prompt revisions' groundedness records, both retained, to compare |
| T025 | The fixture's `fail` record, retained and retrieved |
| T028 | A quickstart run end to end, which contains all of the above |
| T031 | F6 itself — one untested hypothesis left: service-driven adaptive sampling |
| T034 | `infra/DEPLOY.md` — deliberately deferred, since touching `infra/**` arms the CI gate |

T029 (SC-008's deferred cost reading) is **not deferred any more, it is
unavailable**: it needed a day of Cost Management data against a live resource
group, and teardown removed the subject. The at-rest claim is unchanged and was
never in doubt — nothing this block created bills while idle — but the
measured-zero confirmation would need a fresh deployment left standing
overnight.

The evaluations themselves ran correctly every time. What is unproven is the
retrieval of specific records, not the scoring behind them.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T002 and T003 parallelizable with
  each other; T001 independent of both, but must complete before T007's
  deploy targets the same resource group name
- **Foundational (Phase 2)**: Depends on T001–T002 (soft-delete cleared,
  resource group exists) — BLOCKS all user stories' Azure-side work
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2). No
  dependency on US2 or US3
- **User Story 2 (Phase 4)**: T015 has no dependency and can start as soon as
  Setup is done (a `.prompty` file needs no Azure resource). T017–T019 depend
  on Foundational (a deployment to call) and on T009/T010 (US1's
  `evaluate_call.py`/`query_evaluations.py` must exist to be extended) — the
  one deliberate cross-story integration point, consistent with this
  feature's own Assumption that the evaluation mechanism is shared
- **User Story 3 (Phase 5)**: T021 has no dependency (a fixture file needs no
  Azure resource, no call). T022 depends on T009 (`evaluate_call.py` must
  exist to be extended). T023 depends on a real call existing (T011 or T017)
- **Polish (Phase 6)**: T026 can start once enough of Phases 3–5 exist to
  describe; T027 depends on all prior phases' calls and evaluations existing
  to be counted; T029 and T030 depend on Phase 2's deployment existing at all,
  and on each other in that order (teardown destroys the subject of the cost
  measurement, per feature 006's own T027/T028 ordering)

### User Story Dependencies

- **User Story 1 (P1)**: Independent after Foundational — the MVP
- **User Story 2 (P2)**: Its prompt file and git history (T015, T016, T020)
  are provable without US1; scoring the two revisions (T017–T019) reuses
  US1's `evaluate_call.py`/`query_evaluations.py`, a convenience rather than a
  hard requirement — the scripts could be duplicated instead, and aren't only
  because that would contradict this feature's own minimalism
- **User Story 3 (P2)**: T021 (the fixture) is independent of everything.
  T023 (the passing case) needs a real call to exist, from either US1 or US2

### Within Each User Story

- The script that reads a trace (`evaluate_call.py`'s `--trace-id` path)
  before the script that reads an evaluation (`query_evaluations.py`) — the
  second has nothing to retrieve without the first
- `az bicep build` before `what-if` before `az deployment group create` —
  never skip a step (constitution Principle V), even though the template is
  unchanged
- Verification task last, reading from the live trace store, never from what
  a script printed earlier in the same session

### Parallel Opportunities

- T002 and T003 (Setup) — different concerns, no shared file
- T015 (US2's prompt file) and T021 (US3's fixture) can be authored any time
  after Setup, in parallel with Phase 2's Azure work — neither touches an
  Azure resource or a shared file
- T026 (README draft) can start once enough of Phases 3–5 exist to describe,
  in parallel with T027–T028

---

## Parallel Example: Setup and the two story-specific content files

```bash
# Setup, run together:
Task: "Create the resource group rg-ai300-foundry"
Task: "Scaffold qa-observability/foundry-block4/pyproject.toml"

# Once Setup is done, US2's prompt and US3's fixture need nothing from
# Phase 2's Azure work and can be authored while the redeploy is in flight:
Task: "Create qa-observability/foundry-block4/prompts/grounded-qa.prompty"
Task: "Author qa-observability/foundry-block4/fixtures/unsupported_claim.json"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — the redeploy blocks every story)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run T012–T014 independently of Phases 4–5
5. This alone demonstrates Domain 4's core objective — a retrievable quality
   score — before either extension exists

### Incremental Delivery

1. Setup + Foundational → the redeployed Foundry base, verified identical to
   feature 006's
2. Add User Story 1 → validate independently (MVP)
3. Add User Story 2 → validate independently — a comparison with a stated
   direction
4. Add User Story 3 → validate independently — groundedness, both directions
5. Polish → README, invocation count against SC-006, deferred cost reading,
   teardown

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No unit-test suite: each phase's last tasks are the verification, reading
  from the live trace store rather than from anything held in memory —
  consistent with block 3's own "the retrieval is the test" posture
- Every mutating Azure call (T001's purge, T007's deploy, T030's teardown) is
  an explicit, author-authorized action in the session it happens — never
  folded into a task that looks read-only
- Commit after each task or logical group, split so the artifacts stay
  distinguishable (per the author's own preference this session) rather than
  landing as one lump
- Stop at any checkpoint to validate a story independently
