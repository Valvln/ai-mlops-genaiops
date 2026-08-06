---

description: "Task list for the Azure ML workspace Bicep change"
---

# Tasks: Azure ML Workspace in the shared infrastructure template

**Input**: Design documents from `/specs/001-azure-ml-workspace/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: No test tasks. The spec asks for local validation, not a test suite,
so verification is expressed as assertions against the compiled ARM JSON. Those
assertions are the tests, and they live in [quickstart.md](./quickstart.md).

**Organization**: Tasks are grouped by user story. Read the note below before
assuming the groups are independent work streams.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

This feature is infrastructure as code, not application code. There is no `src/`
or `tests/`. **Every implementation task edits one file: `infra/main.bicep`.**
Verification tasks read `infra/main.json`, the gitignored build output.

## How this differs from a typical task list

Two honest notes, so the structure below is not misread:

1. **Parallelism is almost absent.** `[P]` means "different files, no shared
   dependency". Since every implementation task edits the same file, only the
   read-only assertions against the compiled JSON carry `[P]`. Do not expect to
   split this feature across people.

2. **User stories 2 and 3 are attributes of the resource added in story 1**, not
   separate resources. The phases still deliver independent, checkable
   increments — US2 adds the SKU and proves nothing billable crept in, US3 adds
   the identity — but in practice an implementer will likely write them as three
   small edits to one resource block in a single sitting. The split exists for
   checkpointing, not for staffing.

---

## Phase 1: Setup (Baseline)

**Purpose**: Record the "before" state so every later count is a comparison, not
an assertion in a vacuum.

- [ ] T001 Run `az bicep build --file infra/main.bicep` from the repo root and
      confirm it exits 0 with no output; record that `infra/main.json` contains
      exactly 2 resources and 2 outputs, using the `jq` commands in
      [quickstart.md](./quickstart.md)

**Checkpoint**: Baseline is 2 resources, 2 outputs, clean build.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The parameter every later resource declaration depends on.

**⚠️ CRITICAL**: T002 blocks all user story work.

- [ ] T002 Add the `workspaceName` parameter to `infra/main.bicep`, defaulting
      to `'ai300ml${uniqueString(resourceGroup().id)}'`, placed alongside the
      existing `storageAccountName` and `keyVaultName` parameters and following
      their exact style (see the parameters table in [the interface
      contract](./contracts/template-interface.md))
- [ ] T003 Rebuild and confirm the build is still clean and the resource count
      is still 2 — a parameter alone declares nothing

**Checkpoint**: Parameter surface extended, no resource change yet.

---

## Phase 3: User Story 1 - Declare the workspace on the existing foundation (Priority: P1) 🎯 MVP

**Goal**: The template declares a machine learning workspace wired by symbolic
reference to the storage account and key vault already present, plus the
telemetry resources it requires.

**Independent Test**: Build the template and confirm the compiled output holds 5
resources, the ML workspace among them, with its storage and key vault links
expressed as ARM `resourceId(...)` expressions rather than literal ids.

### Implementation for User Story 1

- [ ] T004 [US1] Add the Log Analytics workspace resource to `infra/main.bicep`
      using API version `2025-07-01` (see [research.md](./research.md) R3 for
      why this is not the newest GA version), with `sku.name: 'PerGB2018'`,
      `retentionInDays: 30`, a name derived from
      `uniqueString(resourceGroup().id)`, and the standard project tags
- [ ] T005 [US1] Add the Application Insights component to `infra/main.bicep`
      using API version `2020-02-02`, with the `kind` and `Application_Type`
      both set to `web`, `IngestionMode` set to `LogAnalytics`, and
      `WorkspaceResourceId` referencing the Log Analytics resource added in
      T004 (depends on T004)
- [ ] T006 [US1] Add the machine learning workspace to `infra/main.bicep` using
      API version `2026-05-01`, named from the `workspaceName` parameter, with
      `properties.storageAccount`, `properties.keyVault`, and
      `properties.applicationInsights` referencing the existing
      `storageAccount`, the existing `kv`, and the component from T005 by
      symbolic `.id` — and with **no `containerRegistry` property written at
      all** (depends on T005)
- [ ] T007 [US1] Rebuild and confirm: exit 0, **no output whatsoever** (a
      `BCP081` warning here means a wrong API version), 5 resources, and the
      type list matches the order in [quickstart.md](./quickstart.md)

**Checkpoint**: The workspace exists in the template and compiles. This is the
MVP — everything after it refines properties of what T006 declared.

---

## Phase 4: User Story 2 - Keep the environment inside the free-trial budget (Priority: P2)

**Goal**: The workspace sits on the entry-level tier and nothing billable was
pulled in behind it.

**Independent Test**: Read the compiled JSON. No container registry association,
no compute resource of any type, entry-level SKU, consumption-based telemetry.

### Implementation for User Story 2

- [ ] T008 [US2] Add `sku: { name: 'Basic', tier: 'Basic' }` to the machine
      learning workspace in `infra/main.bicep` (depends on T006)
- [ ] T009 [P] [US2] Assert absence of a container registry: grep
      `infra/main.json` for `containerRegistry` and confirm zero matches
      (SC-003)
- [ ] T010 [P] [US2] Assert no compute was declared: confirm no resource type in
      `infra/main.json` contains `computes`, `computeInstance`, or
      `computeCluster` (FR-008)
- [ ] T011 [P] [US2] Assert the telemetry resources are consumption-billed: Log
      Analytics `sku.name` is `PerGB2018` and `retentionInDays` is `30`
      (FR-004a)
- [ ] T012 [US2] Rebuild and confirm the SKU landed: the workspace's `sku` in
      `infra/main.json` is `{"name": "Basic", "tier": "Basic"}` — exact command
      under "FR-006 — Basic SKU" in [quickstart.md](./quickstart.md) (FR-006)

**Checkpoint**: Cost discipline is demonstrable from the compiled artifact
alone, with no deployment and no billing console.

---

## Phase 5: User Story 3 - Access through a managed identity (Priority: P2)

**Goal**: The workspace requests its own platform-managed identity, so later
role assignments need no secret.

**Independent Test**: The compiled workspace resource carries an `identity.type`
of `SystemAssigned`.

### Implementation for User Story 3

- [ ] T013 [US3] Add `identity: { type: 'SystemAssigned' }` to the machine
      learning workspace in `infra/main.bicep` (depends on T006)
- [ ] T014 [US3] Rebuild and assert the workspace's `identity.type` in
      `infra/main.json` is `SystemAssigned` — exact command under "FR-005" in
      [quickstart.md](./quickstart.md) (FR-005)

**Checkpoint**: The identity the next feature will attach role assignments to
now exists in the template.

---

## Phase 6: User Story 4 - Hand the identifiers downstream (Priority: P3)

**Goal**: Later work can address the workspace without opening the portal.

**Independent Test**: The compiled template publishes both the workspace name
and its full resource id.

### Implementation for User Story 4

- [ ] T015 [US4] Append `workspaceName` and `workspaceId` outputs to
      `infra/main.bicep`, after the existing `storageAccountName` and
      `keyVaultUri` outputs, leaving those two untouched (depends on T006)
- [ ] T016 [US4] Rebuild and assert `jq '.outputs | keys[]'` on
      `infra/main.json` returns exactly `keyVaultUri`, `storageAccountName`,
      `workspaceId`, `workspaceName` (SC-005)

**Checkpoint**: All four user stories are represented in the template.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T017 [P] Assert no hardcoded identifiers: grep `infra/main.json` for GUID
      patterns, excluding `templateHash`, and confirm zero matches; confirm the
      key vault `tenantId` is still the expression `[subscription().tenantId]`
      (SC-004, FR-011)
- [ ] T018 [P] Assert tag consistency: all three new resources in
      `infra/main.json` carry `project: ai300-prep` and `environment: learning`,
      matching the two pre-existing resources (FR-009)
- [ ] T019 Run the full one-shot validation script from
      [quickstart.md](./quickstart.md) and confirm every success criterion
      SC-001 through SC-007 passes
- [ ] T020 Confirm `git status` does not list `infra/main.json` — the build
      artifact stays untracked (constitution principle II)
- [ ] T021 Draft candidate README text for the project author covering the four
      decisions worth recording: no container registry, system-assigned
      identity, workspace-based Application Insights forcing a fifth resource,
      and the deliberate choice of a non-latest Log Analytics API version to
      keep local type-checking. **The author writes and owns the final text**
      (constitution principle IV)
- [ ] T022 Show the complete `git diff` of `infra/main.bicep` and propose the
      commit. Report the change as *validated to compile*, never as *verified to
      work* — no deployment was performed (constitution principles III and V)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Phase 1 — blocks all user stories
- **User Story 1 (Phase 3)**: depends on Phase 2. Blocks US2, US3, and US4,
  because all three modify or read the resource T006 declares
- **User Stories 2, 3, 4 (Phases 4–6)**: each depends on T006 only, so their
  order among themselves is free
- **Polish (Phase 7)**: depends on all preceding phases

### Within User Story 1

Strictly sequential: T004 → T005 → T006 → T007. Each resource references the one
before it, so the chain cannot be reordered or collapsed.

### Parallel Opportunities

Genuinely parallel tasks are the read-only assertions against the compiled JSON:
**T009, T010, T011** within US2, and **T017, T018** in polish. They touch no
file and depend only on a build having happened.

Every other task edits `infra/main.bicep`. Running two of those at once means
two writers on one file — do not.

---

## Parallel Example: User Story 2 assertions

```bash
# After T008 has been written and the template rebuilt, these three read-only
# checks are independent of each other:
grep -c containerRegistry infra/main.json || echo "none - OK"
jq -r '.resources[].type' infra/main.json | grep -i compute || echo "no compute - OK"
jq -r '.resources[] | select(.type|endswith("OperationalInsights/workspaces")) | .properties.sku.name' infra/main.json
```

---

## Implementation Strategy

### MVP First

1. Phase 1 baseline → Phase 2 parameter → Phase 3 workspace
2. **STOP and VALIDATE**: T007 must give a clean build and 5 resources
3. At this point the feature's core value exists: the learning environment is
   declared in one reviewable file

### Incremental Delivery

Phases 4, 5, and 6 each add one property or output and one assertion. Any of
them can be stopped at without leaving the template broken — the build stays
green throughout, because each addition is a valid-on-its-own property of an
already valid resource.

### On committing

The template's default advice is "commit after each task". **That does not apply
here.** Constitution principle III requires the author to review a diff and
authorize each commit, and principle V requires validation to pass first. The
whole `infra/main.bicep` change is one logical change and belongs in one commit,
proposed at T022 — not twenty commits, and none of them automatic.

---

## Notes

- `[P]` tasks = different files or read-only, no dependencies
- `[Story]` labels map tasks to spec.md user stories for traceability
- No deployment task exists anywhere in this list, by design (FR-013)
- Stop at any checkpoint; the template compiles at every one of them

