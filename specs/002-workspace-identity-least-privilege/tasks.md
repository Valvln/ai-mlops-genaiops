---

description: "Task list for feature 002 — least-privilege permissions for the workspace identity"
---

# Tasks: Least-privilege permissions for the workspace identity

**Input**: Design documents from `/specs/002-workspace-identity-least-privilege/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/role-assignments.md](contracts/role-assignments.md), [quickstart.md](quickstart.md)

**Tests**: No test tasks. The specification asks for verification against a live
environment, not for a test suite; the verification steps live in Phase 6 and
are traceable to the success criteria they settle.

**Organization**: grouped by user story, with one deliberate ordering deviation
explained below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different targets, no dependency on incomplete work
- **[Story]**: which user story the task serves (US1–US4)
- Every task names the file it changes or the artifact it produces

## Cost

**Zero.** Every task is either a local file edit, a read against Azure, or a
role assignment change. Role assignments are control-plane metadata and are not
billed. No task creates a resource, changes a service tier, or provisions
compute.

## Two ordering rules that override priority

1. **User Story 4 runs first.** The spec ranks it P2 by value, but its artifact —
   the way back — must exist *before* anything is removed. Writing the reversal
   after the removal would mean reconstructing it from an environment that has
   already changed. This is a sequencing constraint, not a re-prioritisation.
2. **Phase 4 must not be interrupted.** Deleting the platform's blob grant opens
   the only unavoidable permission gap, and the deployment closes it. Never stop
   between T014 and T016.

---

## Phase 1: Setup

**Purpose**: tooling and a place to keep evidence

- [ ] T001 Confirm `az` is reachable and the ML extension is present: `export PATH="/usr/local/bin:$PATH"` then `az extension add --name ml --yes` (already installed at version 2.44.1 during planning; the command is idempotent)
- [ ] T002 Create the evidence directory `specs/002-workspace-identity-least-privilege/evidence/` and add it to `.gitignore` if command output is to be kept out of the repository, or decide to paste findings into the task notes instead

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: capture what cannot be reconstructed later, and settle the one open decision

**⚠️ CRITICAL**: no removal may happen until this phase is complete. The
assignment names captured in T003 are the only way to address the grants for
deletion, and they cease to exist once deleted.

- [ ] T003 Capture the four current grants **with their assignment names** into `specs/002-workspace-identity-least-privilege/evidence/grants-before.json` using the baseline command in [quickstart.md](quickstart.md); confirm the result contains exactly 4 entries
- [ ] T004 [P] Capture the service-side baseline into `evidence/diagnose-before.json` via `az ml workspace diagnose`; confirm every result array is empty
- [ ] T005 [P] Capture the resource inventory into `evidence/resources-before.txt` via `az resource list -g rg-ai300-test01`; confirm it lists exactly 5 resources
- [x] T006 **Author decision required** — settle the open question in [research.md](research.md) R6: whether the vault grant is secret **read** (proposed) or secret **write**. **Done 2026-08-07: secret read (Key Vault Secrets User)**, taken deliberately on incomplete evidence; the unverified inference and the widening path are recorded in `research.md` R6

**Checkpoint**: the baseline is recorded, the vault role is decided, and every
grant can still be addressed by name.

---

## Phase 3: User Story 4 - Be able to put the permission back (Priority: P2, sequenced first)

**Goal**: the way back exists in writing before anything is taken away.

**Independent Test**: read the recorded reversal and confirm every step is a
command that runs as written, with no step that says to look something up.

- [ ] T007 [US4] Add a "Workspace identity permissions" section to `infra/DEPLOY.md` recording what the identity held before this feature, what each of the four grants allowed, and why three of them are being removed
- [ ] T008 [US4] Add the reversal to that section of `infra/DEPLOY.md`: one restore command per removed grant, copied from [contracts/role-assignments.md](contracts/role-assignments.md), using `--assignee-object-id` with an explicit principal type rather than `--assignee`
- [ ] T009 [US4] Add to that section the table of expected future failures from [quickstart.md](quickstart.md) — which capability will break, and which grant restores it — so a later failure is recognised rather than diagnosed
- [ ] T010 [US4] Verify the reversal satisfies SC-010: count the removals (3) and the restore commands, and confirm the counts match and that no command depends on a value not written down

**Checkpoint**: every removal in this feature is now reversible from the runbook
alone. Removals may begin.

---

## Phase 4: User Story 2 - Make every surviving permission visible in the template (Priority: P1)

**Goal**: the template declares both surviving permissions and owns them.

**Independent Test**: read `infra/main.bicep` and enumerate the permissions it
declares; the set matches what the identity holds.

- [ ] T011 [US2] Add the two role definition variables to `infra/main.bicep` using `subscriptionResourceId`, exactly as specified in [contracts/role-assignments.md](contracts/role-assignments.md) — no literal subscription identifier
- [ ] T012 [US2] Add the two role assignment resources to `infra/main.bicep` at API version `2022-04-01`, each with `scope` set to the resource symbol, `name` derived by `guid()`, `principalId` from `mlWorkspace.identity.principalId`, and `principalType: 'ServicePrincipal'`
- [ ] T013 [US2] Validate compilation: `az bicep build --file infra/main.bicep` must exit 0 with **no output** (SC-001). Any warning is a finding — stop and resolve it before continuing
- [ ] T014 [US2] Delete the platform's blob grant (C2) per [contracts/role-assignments.md](contracts/role-assignments.md). **This opens the only permission gap in the feature — do not stop here**
- [ ] T015 [US2] Dry run: `az deployment group what-if -g rg-ai300-test01 --template-file infra/main.bicep`. Confirm zero resources created, deleted, or modified, and exactly 2 role assignments to create (SC-002). Save the output to `evidence/what-if-before-deploy.txt`
- [ ] T016 [US2] Deploy: `az deployment group create -g rg-ai300-test01 --template-file infra/main.bicep --name ai300-rbac-002`. The blob gap closes here
- [ ] T017 [US2] Confirm idempotence (SC-008): re-run the dry run with no edits and confirm it reports no change whatsoever

**Checkpoint**: both surviving permissions are declared and owned by the
template. The identity now holds five grants — two declared, three still to be
removed.

---

## Phase 5: User Story 1 - Take away the permission that exceeds any nameable need (Priority: P1)

**Goal**: nothing the identity holds is scoped above a single resource, and
nothing confers authority no need can be named for.

**Independent Test**: enumerate the identity's permissions and confirm none is
scoped to the resource group or above.

- [ ] T018 [US1] Delete the key vault administration grant (C4). The declared secret grant already covers the vault, so this opens no gap
- [ ] T019 [US1] Delete the file share grant (C3). **This is the riskiest removal in the feature** — the two file datastores exist today and become unusable by the service until it is re-granted. Confirm the reversal from T008 is in place before running it
- [ ] T020 [US1] Delete the resource-group-wide grant (C1) — the point of the feature
- [ ] T021 [US1] Confirm SC-003: enumerating the identity's grants returns none scoped to the resource group or above
- [ ] T022 [US1] Confirm SC-004: the identity holds exactly 2 grants, and they are exactly the 2 the template declares — no more, no fewer
- [ ] T023 [US1] Confirm SC-005: inspect the two role definitions and verify neither confers wildcard authority over a resource type, the ability to create or delete resources, or the ability to change the access configuration of its resource
- [ ] T024 [US1] Confirm SC-007: `az resource list -g rg-ai300-test01` still returns the same 5 resources with the same names as `evidence/resources-before.txt`

**Checkpoint**: the reduction is complete and the permissions are as intended.
Whether the workspace still works is not yet known — that is Phase 6.

---

## Phase 6: User Story 3 - Confirm the workspace still works (Priority: P2)

**Goal**: evidence, not argument, that the reduction did not break the workspace.

**Independent Test**: a service-side operation succeeds, **and** the same
operation is seen to fail when its permission is withheld.

**⚠️ The trap this phase exists to avoid**: the author holds Owner, so almost any
command run by hand succeeds regardless of what the identity can do. A passing
result means nothing until the negative control shows the check can fail.

- [ ] T025 [US3] Run `az ml workspace diagnose` and compare against `evidence/diagnose-before.json`; save to `evidence/diagnose-after.json`
- [ ] T026 [US3] Establish the probe's sensitivity — the negative control required by FR-004a: delete the declared blob grant, re-run `diagnose`, record whether it reports anything, then redeploy the template to restore the grant and confirm the probe is clean again. **Restoring is not optional** (SC-011)
- [ ] T027 [US3] Record the verdict honestly. If the probe reported a problem while the grant was absent, SC-006 is satisfied and `diagnose` is established as evidence. If it stayed clean, `diagnose` does not test this permission — **report SC-006 as unverified with the reason**, and do not substitute a command that appears to prove the point without doing so
- [ ] T028 [US3] Run `az ml workspace sync-keys` as the control-plane probe. If it fails, record it as a finding — **do not treat it as an FR-016 trigger**. Nothing in this project consumes it, and under FR-004 a capability with no consumer does not justify a permission
- [ ] T029 [US3] If any verification shows the workspace lost something it actually needs, apply FR-016: restore the permission immediately from the T008 reversal, record which operation failed and which grant covered it, and **stop for the author to decide**. Do not re-grant and then write the justification to match
- [ ] T030 [US3] Confirm SC-011: re-run the verification as the last action and confirm the environment is left working, with no permission gap open

**Checkpoint**: the reduction is verified, or its verification is honestly
reported as inconclusive. Either way the environment works.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Update the "Verify" and "Summary checklist" sections of `infra/DEPLOY.md` so the permission checks sit alongside the existing resource checks, and correct the runbook's expected state to reflect the two declared grants
- [ ] T032 [P] Draft candidate `README.md` text in the author's first person covering what was reduced and why, for the author to rewrite and commit (constitution principle IV — Claude drafts, the author owns)
- [ ] T033 [P] Update `tracker_ai300.local.md`: the Week 1 row "Gestione identità e accesso (RBAC, managed identity)" moves from 🔄 to ✅, since role assignments have now been exercised for real. Written in Italian, and kept free of anything derivable from the repo
- [ ] T034 Add the flashcards this feature produced to `FLASHCARDS.local.md` — at minimum: Owner grants no Key Vault data-plane access under RBAC; a duplicate role assignment under a different name is rejected; `2022-04-01` is the latest GA role assignment API version
- [ ] T035 Decide whether to keep the `az ml` extension installed; if not, `az extension remove -n ml`. Note the decision in `infra/DEPLOY.md` prerequisites

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: depends on Phase 1 — **blocks everything**, because the assignment names it captures cannot be recovered after deletion
- **Phase 3 (US4)**: depends on Phase 2 — **blocks every removal**
- **Phase 4 (US2)**: depends on Phase 3
- **Phase 5 (US1)**: depends on Phase 4 — the vault grant must exist before the vault administration grant is deleted
- **Phase 6 (US3)**: depends on Phase 5 — verification is meaningless before the reduction is complete
- **Phase 7 (Polish)**: depends on Phase 6

### Why the user stories are not independent here

The template's usual promise — each story independently deliverable — does not
hold for this feature, and pretending otherwise would produce a misleading plan.
The environment is live and singular:

- US1 without US2 leaves the identity without the permissions the template would
  have declared.
- US2 without US1 leaves the resource-group grant in place, so the reduction has
  not happened.
- US3 verifies US1 and US2 and has nothing to verify on its own.
- US4 is a prerequisite for US1 by sequencing.

The stories remain useful as units of *value* and traceability. They are not
units of independent delivery.

### Parallel opportunities

Genuinely parallel work is limited, because most tasks act on one live
environment in sequence:

- T004 and T005 (baseline captures) run in parallel with each other
- T031, T032, T033 (documentation) run in parallel with each other

Everything else is sequential by dependency or by safety.

---

## Traceability

| Success criterion | Settled by |
| --- | --- |
| SC-001 build clean | T013 |
| SC-002 dry run shows only grants | T015 |
| SC-003 nothing above a single resource | T021 |
| SC-004 held set equals declared set | T022 |
| SC-005 no create/delete or access governance | T023 |
| SC-006 service-side proof, with negative control | T025, T026, T027 |
| SC-007 five resources unchanged | T024 |
| SC-008 redeploy changes nothing | T017 |
| SC-009 cost $0 | by construction — no task creates a billable thing |
| SC-010 reversal complete and runnable | T010 |
| SC-011 environment left working | T030 |

| Requirement | Delivered by |
| --- | --- |
| FR-001, FR-002 scope reduction | T018–T021 |
| FR-003 everything declared | T011, T012, T022 |
| FR-004, FR-005 narrow to stated need | T006, T023 |
| FR-004a service-side proof | T026, T027 |
| FR-006 deterministic naming | T012, T017 |
| FR-007, FR-008 no literals | T011, T012 |
| FR-009, FR-010, FR-011 no new resource, no secret, one principal | T015, T024 |
| FR-012 reversal recorded | T007–T009 |
| FR-013 removal separately authorized | T014, T018–T020 |
| FR-014 API version verified | done in planning (research.md R1) |
| FR-015 validate before commit | T013, T015 |
| FR-016 restore on failure | T029 |

---

## Commit boundaries

One logical change per commit, each proposed to the author with a diff
(constitution principle III). Suggested boundaries:

1. **T007–T010** — the runbook's permissions section and reversal. Committed
   *before* anything is removed, so the way back is in git history first.
2. **T011–T013** — the template change, once it compiles clean.
3. **T031, T032, T033, T034** — documentation after the outcome is known.

Live-environment acts (T014, T016, T018–T020, T026) are not commits. Each is a
separate authorization the author gives before it runs.

---

## Notes

- Nothing here is validated yet. `az bicep build` runs at T013 and the dry run at
  T015; until then this is a plan, not a verified change.
- The riskiest single step is T019. Confirm T008 is written and committed before
  running it.
- The most likely thing to go wrong quietly is T027 — reporting a clean probe as
  a pass when the probe was never sensitive to the permission in the first place.
