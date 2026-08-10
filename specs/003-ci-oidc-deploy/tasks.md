# Tasks: Deployment from continuous integration, without a stored secret

**Input**: Design documents from `/specs/003-ci-oidc-deploy/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: No unit or contract test suite is generated — this feature has no
application code. Its tests are the workflow runs themselves and the four
in-workflow boundary assertions, which appear as ordinary tasks below.

**Organization**: Tasks are grouped by user story, in the priority order of
[spec.md](spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files or different control planes, no
  dependency on an incomplete task)
- **[Story]**: which user story the task belongs to (US1…US5)
- Every task names the file it writes

## Path conventions

Three control planes, only one of which is the repository:

| Where the work lands | Path |
| --- | --- |
| Templates | `infra/` |
| Workflows | `.github/workflows/` |
| Specification artifacts | `specs/003-ci-oidc-deploy/` |
| Entra and Azure objects | no path — the task records its outcome as described below |

**Before any `az` or `gh` command**: `export PATH="/usr/local/bin:$PATH"`.

### Where evidence goes, and why it is two places

`specs/**/evidence/` is **gitignored**, deliberately: *"Evidence of a run, not a
source of truth: findings that matter are written into the spec artifacts and the
deployment runbook instead."* Feature 002 followed that convention — its
`evidence/` directory exists locally and is tracked by nothing.

This feature's exit criterion, however, **is** the evidence. FR-016 wants the
exact command and the exact error, and evidence that lives only on the author's
machine settles nothing for anyone reading the repository.

Both hold, without amending `.gitignore`:

| | Path | Tracked? | Contents |
| --- | --- | --- | --- |
| Raw capture | `specs/003-ci-oidc-deploy/evidence/` | no | full command output, run logs, JSON inventories, unredacted |
| Closing record | `specs/003-ci-oidc-deploy/results.md` | **yes** | the commands and errors that settle each criterion, verbatim but redacted |

`results.md` is what the criteria are read from. `evidence/` is the working
material it was distilled from — which is precisely the split the `.gitignore`
comment asks for.

**Redaction rule, binding on `results.md`.** `origin` is public. R10 chose to
store the tenant, subscription and client identifiers as secrets rather than
variables precisely so they are not published; the same reasoning applies to a
tracked record. `results.md` elides them the way [research.md](research.md) does
— `5900fbc9-…` — and never carries a full identifier. Everything else is copied
verbatim, and each elision is marked where it is applied. `evidence/` is not
redacted, because it never leaves the machine.

---

## Phase 1: Setup — the objects the author creates

**Purpose**: bring into existence everything CI cannot create for itself
([data-model.md](data-model.md)). Nothing here is deployed by CI, and nothing
here costs anything.

- [X] T001 Capture the six-resource baseline to `specs/003-ci-oidc-deploy/evidence/inventory-before.json` using the `az resource list` command in [quickstart.md](quickstart.md). This must be taken before any other task; SC-002 is a diff against it.
- [X] T002 [P] Register the `ai300-github-deploy` application and its service principal with `az ad app create` / `az ad sp create`, adding **no** password and **no** certificate at any point (FR-002), and record the client id and the service principal object id in `specs/003-ci-oidc-deploy/evidence/identity-ids.md` — unredacted, because that file is gitignored and the ids are needed by later tasks.
- [X] T003 [P] Create the empty probe resource group `rg-ai300-probe` in `northeurope` and note its creation in `specs/003-ci-oidc-deploy/evidence/identity-ids.md`. It holds nothing and exists only so probe P2 has a named target (FR-017b).
- [X] T004 Enumerate the application's credentials with both `az ad app credential list` forms and append the two zero counts to `results.md` under **No credential ever existed** as the *before* half of SC-006. Depends on T002.
- [X] T005 Create the GitHub environment `azure-deploy` with the author as required reviewer, **Prevent self-review off** (R5), deployment branches limited to `main`, and record the resulting settings in `results.md` under **The gate and what is stored**.
- [X] T006 Store `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` as repository secrets via `gh secret set`, and record in `results.md` under **The gate and what is stored** that these are identifiers, not credentials (R10) — the claim SC-004's third refusal exists to settle. Depends on T002.

**Checkpoint**: the identity exists and can be named, but nothing trusts it yet.

---

## Phase 2: Foundational — trust and authority

**Purpose**: the trust condition and the grant. **No user story can begin until
this phase completes**, because until it does every authentication fails for the
uninteresting reason that nothing is configured.

**⚠️ The order in this phase is forced.** T007 must produce the subject before
T008 can be written, and getting it wrong costs a gate approval per attempt (R3).

- [X] T007 Add `.github/workflows/oidc-claims-probe.yml` — a temporary workflow, `workflow_dispatch` only, `id-token: write`, **no `environment:`** — that requests a token and prints only its `sub`, `aud` and `iss` claims. **The token itself is never printed**, only the three claims decoded out of it (R3).
- [X] T008 Run `oidc-claims-probe.yml` and record the observed subject verbatim in `results.md` under **The observed subject**, alongside the format R3 predicted. If the two differ, the observed value wins and R3 is annotated with what was actually issued — observation over documentation, including over R3's own.
- [X] T009 Create the federated identity credential on `ai300-github-deploy` from the **observed** subject in T008, issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and record the created object in `specs/003-ci-oidc-deploy/evidence/identity-ids.md`. Depends on T008.
- [X] T010 Write `infra/ci-identity.bicep`: the custom role definition `AI300 CI Deployer (rg-ai300-test01)` at API `2022-04-01` seeded with **exactly the eight shipping operations** in [contracts/role-definition.md](contracts/role-definition.md), `assignableScopes` holding only this resource group, plus the role assignment to the principal passed as a `principalId` parameter (R8 — no directory identifier is written into the template).
- [X] T011 Validate `infra/ci-identity.bicep` with `az bicep build` and report the result, warnings included, before proposing it for commit (Principle V). Depends on T010.
- [X] T012 [P] Extend `.github/workflows/bicep-validate.yml` so the build step globs every `*.bicep` under `infra/` instead of naming `main.bicep`. No permission is added and no token is requested — a fork pull request must keep running it exactly as today (FR-013, R6).
- [X] T013 Deploy `infra/ci-identity.bicep` as the author with `az deployment group create`, passing the service principal object id, and record the deployment name in `specs/003-ci-oidc-deploy/evidence/identity-ids.md`. Depends on T011.

**Checkpoint**: the identity is trusted from one gated context and holds a
deliberately incomplete grant. Everything from here is discovered by running.

---

## Phase 3: User Story 1 — CI deploys, holding no secret (Priority: P1) 🎯 MVP

**Goal**: a run that genuinely deployed — a record in the deployment history, not
a green check.

**Independent Test**: trigger `infra-deploy.yml`, approve the gate, and confirm
both that the run is green and that `az deployment group list` shows a record
named for that run whose state is `Succeeded`.

- [X] T014 [US1] Write `.github/workflows/infra-deploy.yml` with the `deploy` job only: triggers `push` to `main` on `infra/**` plus `workflow_dispatch`, `environment: azure-deploy`, permissions `id-token: write` and `contents: read` and nothing else, `concurrency` with `cancel-in-progress: false`, actions pinned to the SHAs in [contracts/workflow-contract.md](contracts/workflow-contract.md), and a real `az deployment group create -n ai300-ci-<run_id>` — no preview, no what-if (FR-010).
- [X] T015 [US1] Run the workflow and read the failure. **This is expected**: the seeded role is known-incomplete because the activity log records no reads (R2). Add **only** the operation the error names to `infra/ci-identity.bicep`, add its row to the "Added by verification" table in [contracts/role-definition.md](contracts/role-definition.md) with the failing run id and the error excerpt, redeploy `ci-identity.bicep`, and run again. Repeat until green — expect two to four iterations.
- [X] T016 [US1] Before adding each operation in T015, confirm the failure is an authorization refusal that names it, and not a queued deployment, a transient error, or an unregistered provider (FR-017 applies to discovery as much as to the probes). Record any rejected candidate, with the reason, in `results.md` under **Discovery**.
- [X] T017 [US1] Record the green run id and the `Succeeded` deployment record in `results.md` under **It really deployed**, noting explicitly that the failed records above it are discovery evidence and not counted against SC-001.
- [X] T018 [US1] Capture `specs/003-ci-oidc-deploy/evidence/inventory-after.json` and diff it against `inventory-before.json`; record the empty diff in `results.md` under **It really deployed** (SC-002, FR-011).
- [X] T019 [US1] Re-run the workflow unchanged, confirm it succeeds again and that a second inventory capture still diffs clean, and record both run ids in `results.md` under **It really deployed** (FR-012).

**Checkpoint**: US1 stands alone — CI deploys, with no credential in existence.
Nothing yet proves it cannot do more.

---

## Phase 4: User Story 2 — the reach is proven bounded (Priority: P1)

**Goal**: four refusals, against named targets, recorded with their exact errors.

**Independent Test**: read the `boundary` job of any deployment run — all four
probes exited non-zero with an authorization error, and a probe that succeeded
would have turned the job red.

- [X] T020 [US2] Add the `boundary` job to `.github/workflows/infra-deploy.yml`: runs after `deploy`, same environment, same principal, executing probes P1–P4 exactly as written in [contracts/boundary-probes.md](contracts/boundary-probes.md).
- [X] T021 [US2] Implement the assertion rule in that job: a probe passes only when the command exits non-zero **and** its stderr names an authorization refusal. A probe that succeeds fails the run; a probe that fails for any other reason also fails the run (FR-017a). This is what makes SC-003 a standing test rather than a one-day capture.
- [X] T022 [US2] Run the workflow and copy the four commands and their errors verbatim into `results.md` under **Four authorization refusals**, one section per probe, with the run id — the exact command and the exact error, not a description of why the configuration forbids it (FR-016).
- [X] T023 [US2] For each of the four, state in the same file which axis it settles — P1, P2, P3 outside the scope; P4 inside the scope and outside the authority — and confirm none was satisfied by an empty result (FR-017a, SC-003).
- [X] T024 [US2] If any probe unexpectedly succeeded, delete what it created immediately, record the fact as a defect in `results.md` under **Four authorization refusals**, and narrow `infra/ci-identity.bicep` before continuing. A widened boundary is the one failure mode of this feature that is not normal.

**Checkpoint**: the boundary is demonstrated, and demonstrated on every future
run.

---

## Phase 5: User Story 3 — only the trusted context can become the identity (Priority: P2)

**Goal**: three refusals, all at authentication, before any authorization
decision.

**Independent Test**: each of the three attempts fails with an authentication
error. An authorization error anywhere here would mean the context was trusted
after all — a finding, not a pass.

- [X] T025 [US3] Re-run `oidc-claims-probe.yml` on `main` **now that the federated credential exists**, with an `azure/login` step and no `environment:`, and capture the refusal in `results.md` under **Three authentication refusals** as A1. This is the sharp version of SC-004's first refusal: correct repository, correct branch, gate not passed. The setup-time failure from T008 is the weak version — it proves only that nothing was configured yet — and is recorded alongside it as such. The run needs no gate approval, precisely because it does not enter the environment.
- [X] T026 [US3] Run the same probe from the feature branch rather than `main`, so the subject names a `ref` context that satisfies the trust condition not at all, and capture the refusal as A2 in `results.md` under **Three authentication refusals**.
- [X] T027 [US3] Attempt `az login --service-principal` from the author's machine using only the three stored identifiers and a junk federated token, and capture the refusal as A3 in the same file (SC-004 #3, the check that settles R10's claim).
- [X] T028 [US3] Confirm in `results.md` under **Three authentication refusals** that all three errors are authentication errors — `AADSTS…`, not `AuthorizationFailed` — and say so explicitly, since the distinction is the entire content of the criterion.

**Checkpoint**: what the identity may do is bounded, and who may become it is
bounded.

---

## Phase 6: User Story 4 — pull requests validate and cannot deploy (Priority: P2)

**Goal**: the existing behaviour still works, and the new workflow is unreachable
from it.

**Independent Test**: open a pull request touching `infra/` and read which
workflows ran for it.

- [X] T029 [US4] Open a pull request that modifies something under `infra/`, confirm `bicep-validate.yml` runs green — including on `ci-identity.bicep`, which T012 brought into its build scope — and record the run id in `results.md` under **Pull requests validate, and do not deploy**.
- [X] T030 [US4] Confirm with `gh run list --workflow infra-deploy.yml --event pull_request` that the deploying workflow has **no** run for that event, and record the empty result in `results.md` under **Pull requests validate, and do not deploy** (SC-005, FR-014).
- [X] T031 [US4] Read the validation run's own log of granted token permissions and record in the same file that it holds no `id-token` permission and reads no stored value (FR-013, US4 scenario 3).
- [X] T032 [US4] Record in `results.md` under **Pull requests validate, and do not deploy** the limit this evidence has: no genuine fork pull request was authored, so SC-005 is settled by what the repository runs plus the three independent barriers in R6 — not by a fork actually trying. The checklist already carries this; it belongs with the evidence too.

---

## Phase 7: User Story 5 — no granted authority is inert (Priority: P3)

**Goal**: the grant is what authorizes the deployment, and every operation in it
is load-bearing. This is the check feature 002 would have failed.

**Independent Test**: withdraw the grant, run, fail; restore, run, succeed. Then
walk the role against the provenance table.

- [X] T033 [US5] Walk every operation in the final `infra/ci-identity.bicep` against [contracts/role-definition.md](contracts/role-definition.md) and delete any whose Provenance cell is empty — the record is binding in the destructive direction, and an unaccounted operation is removed, not argued for (FR-006c, FR-008).
- [X] T034 [US5] Redeploy `ci-identity.bicep` after any deletion in T033 and re-run the workflow to confirm the deployment still succeeds. If it now fails, the deleted operation was necessary after all and re-enters the role **with this failure as its provenance** — which is the mechanism working, not a mistake to hide.
- [X] T035 [US5] Withdraw the role assignment with `az role assignment delete`, run the workflow, approve the gate, and record the authorization failure and its run id in `results.md` under **Nothing granted is inert**. A run that still succeeds means something other than this grant is authorizing it — the 002 outcome, and a failed criterion.
- [X] T036 [US5] Restore the assignment by redeploying `infra/ci-identity.bicep`, run the workflow again, and record the succeeding run id in `results.md` under **Nothing granted is inert**. The final state of the environment must be the working one (spec edge case).
- [X] T037 [US5] In `results.md` under **Nothing granted is inert**, tabulate each operation in the final role against the derivation line or verification run that accounts for it, and state the two counts SC-007 compares. Zero operations may survive unaccounted for.

**Checkpoint**: all five stories settled. What remains is writing it down.

---

## Phase 8: Polish & closing

**Purpose**: the parts that make the feature usable by the next person, and the
criteria that can only be checked once everything else has happened.

- [X] T038 Enumerate the application's credentials again with both `az ad app credential list` forms and append the two zero counts, with the date, to `results.md` under **No credential ever existed** as the *after* half of SC-006 — meaningful only because SC-001 has already passed.
- [X] T039 [P] Run the cost report for the days spanning the feature and record it in `results.md` under **Cost**, confirming no new meter and a total of `0.00` (SC-008, FR-019).
- [X] T040 Delete `.github/workflows/oidc-claims-probe.yml`. It has served its two purposes — the subject in T008, the refusals in T025 and T026 — and a workflow that requests a token outside the gate should not outlive them.
- [X] T041 Revise `infra/DEPLOY.md` with the identity runbook: the creation order from [data-model.md](data-model.md), the CI deployment path, the immutable-subject trap (R3), and **the stale-authority warning** — when `main.bicep` gains a resource type the next deployment *will* fail, and that is FR-006 working. The next person must find that written down rather than debug it.
- [X] T042 Write the reversal into `infra/DEPLOY.md` as runnable commands — role assignment, role definition, federated credential, service principal, application, probe resource group, three secrets, environment — and confirm the count of removal commands matches the count of objects created (SC-009, FR-018). The reversal is recorded, not executed; the environment is left working.
- [X] T043 Sweep `specs/003-ci-oidc-deploy/results.md` for full tenant, subscription, client or object identifiers and apply the redaction rule stated at the head of this file. `origin` is public, and R10's reasoning about not publishing identifiers applies to a tracked record as much as to repository variables. `evidence/` is left alone — it is gitignored and never leaves the machine.
- [X] T044 Update `specs/003-ci-oidc-deploy/checklists/requirements.md`: close the two Deferred items (overlapping runs — settled by `cancel-in-progress: false`; where evidence is stored — settled by the `results.md` / `evidence/` split), and confirm the two recorded limits still read honestly.
- [ ] T045 Draft candidate `README.md` text for the author covering feature 003 and its contrast with 002 — the author reviews, rewrites and commits it (Principle IV). Claude does not write the first-person account as though it were his.
- [X] T046 Walk [quickstart.md](quickstart.md) end to end against the finished state and correct anything it now describes wrongly.

---

## Dependencies & execution order

### Phase dependencies

- **Phase 1 (Setup)**: T001 first — the baseline must predate every change. T002/T003 parallel; T004 after T002; T006 after T002.
- **Phase 2 (Foundational)**: strictly sequential T007 → T008 → T009 for the trust condition; T010 → T011 → T013 for the grant. T012 is independent of both. **Blocks every user story.**
- **Phase 3 (US1)**: depends on Phase 2 complete. Blocks US2 and US5.
- **Phase 4 (US2)**: depends on US1 — the `boundary` job runs after `deploy`, so a working deployment must exist first.
- **Phase 5 (US3)**: depends only on T009 (the credential must exist for the refusals to be sharp). Can run in parallel with US1's discovery loop, and costs no gate approvals.
- **Phase 6 (US4)**: depends on T012 and on `infra-deploy.yml` existing (T014) — otherwise "no deploy run for this event" is trivially true and proves nothing.
- **Phase 7 (US5)**: depends on US1 being green. Last by necessity, not by preference.
- **Phase 8**: after everything, except T039 which can be run at any point.

### Story dependencies

- **US1 (P1)** → the MVP. Independent once Phase 2 is done.
- **US2 (P1)** → needs US1.
- **US3 (P2)** → needs only the federated credential. Genuinely independent.
- **US4 (P2)** → needs the deploying workflow to exist. Otherwise independent.
- **US5 (P3)** → needs US1 green.

### Parallel opportunities

Limited, and honestly so — this feature is a sequence of observations, and most
tasks exist to read what the previous one produced.

- T002 ‖ T003 (different control planes)
- T012 ‖ the T007–T009 trust chain (different files, no shared state)
- Phase 5 (US3) ‖ Phase 3's discovery loop — the sharpest parallel win, since US3 needs no gate approval
- T039 ‖ anything

### The loop that is not parallelisable

T015 is a serial loop by construction: run, read the refusal, add one operation,
redeploy the role, run again. Each iteration costs one gate approval. It cannot be
shortened by adding operations speculatively — that is precisely what FR-006a
forbids, and it is how feature 002 produced a grant that did nothing.

---

## Commit boundaries

One logical change each, matching the seams in [plan.md](plan.md). The author
runs every commit (Principle III).

| # | Commit | Tasks |
| --- | --- | --- |
| 1 | `infra/ci-identity.bicep` — the role and its assignment | T010, T011, and each T015/T033 revision as its own follow-up commit |
| 2 | `.github/workflows/infra-deploy.yml` — the deploying workflow | T014, then T020–T021 as a second commit |
| 3 | `.github/workflows/bicep-validate.yml` — the widened build step | T012 |
| 4 | `infra/DEPLOY.md` — runbook and reversal | T041, T042 |
| 5 | `specs/003-ci-oidc-deploy/results.md` — the closing record | T017–T019, T022–T023, T025–T028, T029–T032, T035–T037, T038–T039, T043–T044 |

The probe workflow (T007) and its deletion (T040) are two more commits, small and
worth keeping separate: adding a workflow that requests a token outside the gate,
and removing it again, are both decisions someone might want to find in the
history.

---

## Implementation strategy

### MVP

Phases 1, 2 and 3. At that point continuous integration deploys with no stored
credential — the objective — and the feature is demonstrably incomplete in a way
that is stated rather than hidden: nothing yet proves the identity cannot do more.

### Increments

1. Setup + Foundational → the identity exists, is trusted from one context, holds an incomplete grant
2. **US1** → it deploys (MVP)
3. **US2** → the boundary is proven, and proven on every subsequent run
4. **US3** → and the identity cannot be assumed from anywhere else
5. **US4** → the existing validation path is confirmed intact
6. **US5** → and nothing granted is decoration
7. Polish → written down where the next person will find it

### What "done" means here

The exit criterion is a green run that really deployed plus a refused attempt —
so the feature closes on T037, and Phase 8 is what makes it survivable. Two
failure modes will occur during the work and only one is a problem: a red
`deploy` job means the role is too narrow, which is the method; a red `boundary`
job means the authority is too wide, which is a defect.

---

## Notes

- `[P]` means different files or different control planes, never "probably fine".
- Every criterion in this feature is settled by an attempted action. No task here closes by reading a configuration and forming a judgement — that is what let 002's SC-003 pass while its objective was missed.
- Nothing may be reported as verified before its run exists. `az bicep build` proves a template compiles; only a run proves a deployment.
- The gate approval is the scarce resource. Batch work that does not need it — US3, T012, T039 — around the runs that do.
