# Specification Quality Checklist: Deployment from continuous integration, without a stored secret

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Constitution Alignment

- [x] Cost stated up front, with an estimate (Cost section: zero, itemised)
- [x] Success criteria verifiable by command or observable outcome, not opinion
- [x] No resource names or API versions in the spec (level separation held)
- [x] Written in English

## Notes

### Clarifications resolved during `/speckit-specify` (2026-08-09)

Both were scope-level, both answered toward the narrower option:

- **FR-004** — trust binds to a named approval gate, not to a branch. Adds
  FR-004a (the gate must require a human decision) and a third refusal to SC-004.
- **FR-006** — authority restricted to the resource types the template declares,
  not a predefined general-management role. Adds FR-006a and FR-006b, and a
  fourth refusal to SC-003 on the second axis of the boundary: inside the scope,
  outside the authority.

### Clarifications resolved during `/speckit-clarify` (2026-08-09)

Four asked, four answered. Two of them changed the shape of the work rather than
a detail:

- **Unit of authority for FR-008 / SC-007.** Necessity of individual operations
  is carried by the discovery record; the explicit withdraw-and-rerun test
  applies once, to the grant as a whole. Rewrote FR-008, SC-007, US5. Turned
  roughly fifteen deployment cycles into one, without weakening the check — the
  record is binding destructively (unaccounted operation → deleted).
- **Trigger for the deploying workflow.** Merge on the default branch *and*
  manual dispatch, both gated. Added FR-014a. Manual dispatch is what makes
  SC-004 and SC-007 testable without empty commits.
- **What counts as a refusal.** Only an explicit authorization denial; an empty
  result never counts, because the platform filters enumerations by permission.
  Added FR-017a/FR-017b, rewrote US2 scenario 2 and SC-003. This resolved a real
  contradiction: US2 previously accepted "returns nothing" while SC-003 demanded
  an authorization error. **Consequence**: a second empty resource container is
  needed as a named probe target. Free, and removed by the FR-018 reversal.
- **How discovery is actually performed.** Two observational passes — derive from
  the record of operations the deployment invoked, then verify by deploying as
  the identity. Rewrote FR-006a, added FR-006c. Neither pass consults
  documentation, so FR-006a holds; the derivation pass is what keeps the gated
  approval count at two or three instead of fifteen.

### Two limits recorded rather than hidden

**SC-005 is weaker than it reads.** It settles fork behaviour from what the
repository observably runs for a pull request, plus the authentication refusals
in SC-004 — not from a genuine fork pull request authored by a second account.
Recorded in Assumptions.

**The approval gate is not a separation of duties.** With one author, the person
approving is the person who wrote the change. The spec says so in Edge Cases and
in Assumptions, and claims only the weaker property: a deliberate pause.

### Watch during planning

**Failing deployments are the method, not a defect.** FR-006a establishes the
operation set by deploying and reading what the failure names. The plan must
budget for failed runs and failed deployment records, and must not treat the
first red run as something to debug away.

**The one substitution that would hollow this out**: a plan that pre-computes the
operation list from role documentation would satisfy FR-006 in form while
abandoning FR-006a, FR-006c, and FR-008 — the same shape of mistake as 002's
SC-003. FR-006c is the guard: every operation must trace to a derivation-record
line or a verification failure.

### Deferred, deliberately — both now closed

Two lower-impact items were left for the plan rather than spent as clarification
questions. Both were settled during implementation:

- **Overlapping runs.** ✅ Settled by `concurrency: cancel-in-progress: false` in
  `infra-deploy.yml`. Queueing rather than cancelling, precisely because of the
  FR-017 interaction noted here: a cancelled run produces an error that reads
  like an authorization refusal.
- **Where evidence is stored.** ✅ Settled as a split. `specs/**/evidence/` is
  gitignored by repository convention, so raw captures stay local and
  `results.md` — tracked and redacted — carries the commands and errors the
  criteria are read from. Following 002 exactly would have left this feature's
  exit criterion unreadable to anyone but the author.

### Closed after implementation (2026-08-10)

**The two recorded limits still read honestly.** SC-005 was settled by a
same-repository pull request plus the three barriers in R6, not by a genuine
fork — `results.md` repeats the limit alongside the evidence. The approval gate
remained a deliberate pause: `prevent_self_review` is off, and the author
approved every one of the eleven gated runs.

**"Watch during planning" held.** The operation list was not pre-computed. Five
deployments failed, each naming what it lacked, and the role grew from eight
operations to thirteen. FR-006c did real work: `validate/action` had been
*removed* from the derived set by reasoning, and the first failure put it back.

**One thing this checklist did not anticipate.** It guarded against a plan that
would satisfy FR-006 in form while abandoning its substance. The failure that
actually occurred was one layer down: probe P4 satisfied the *assertion* in form
— non-zero exit, authorization error — while testing an axis nobody had asked
about, because `az identity create` failed on a preliminary resource-group read.
Writing a criterion that cannot be met vacuously is hard; writing an assertion
that cannot *pass* vacuously turned out to be harder, and being alert to the
failure mode was not enough to prevent it. What caught it was reading the
captured error rather than the pass/fail summary.
