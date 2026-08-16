# Specification Quality Checklist: From a job that runs to a model that answers

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-16
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

## Project-specific gates

Derived from `.specify/memory/constitution.md` and from the two defects feature
004 closed with.

- [x] **Cost stated up front** (principle I) — the Cost section gives a per-phase
      estimate at the rates measured 2026-08-16, names the three mechanisms that
      hold it, and identifies the one cost still unknown.
- [x] **Cheapest suitable form chosen** (principle I) — batch endpoint over
      real-time, existing cluster reused, no new billable resource type.
- [x] **Nothing left running** (principle I) — FR-029 and SC-008/SC-012 require
      closure to be read from the service, in both phases.
- [x] **English only** (principle VI) — spec is in English.
- [x] **No resource names in the spec** (CLAUDE.md level rule) — the cluster, the
      data store and the container are referred to by role, never by name.
- [x] **Success criteria verifiable by command or observable outcome**
      (constitution, Development Workflow) — each SC names what is read and what
      it is compared against.
- [x] **Every criterion measures the objective, not a proxy** — the Context
      section tabulates the six cheap checks this feature could have used, and
      each SC is written against the right-hand column.
- [x] **Deferred criteria declared in advance, not discovered at closing time** —
      the Deferred criteria section names SC-007, SC-013 and SC-014 with the date
      each becomes readable. This is the defect feature 004 closed with.
- [x] **Phase 1 is independently closable** — FR-030, SC-008, and User Story 1
      and 2 are both P1 and testable with no registry and no endpoint in
      existence.
- [x] **Carried-over criteria restated when their test no longer works** —
      SC-013 inherits feature 004's load-balancer question and replaces its
      binary test, because this feature's own jobs contaminate it. FR-028 states
      the quantitative replacement.

## Validation notes

**Iteration 1 — three issues found and fixed:**

1. *"The job's cost is known" as a same-day Phase 1 exit criterion.* As handed
   over, this would have repeated feature 004's exact defect: cost data lags 8-24
   hours, so the measured figure cannot exist on 2026-08-16. Split into SC-006
   (billable node time from the job's own timestamps, same-day) and SC-007
   (measured, deferred to 2026-08-17).

2. *The carried-over load-balancer criterion had a test that no longer
   discriminates.* Feature 004 planned to read a day at rest and check whether a
   load-balancer row appears. This feature's training jobs run on that same day
   and produce that row regardless of the answer. Replaced with the quantitative
   form in FR-028.

3. *Two success criteria were phrased as proxies on the first pass* — "the run
   is visible with its metrics" and "the model is saved as an artifact". Both
   rewritten against what they are meant to prove: agreement with an
   independently computed baseline (SC-003) and a retrieved artifact that loads
   and reproduces the baseline's predictions (SC-004).

**Not raised as issues, recorded as accepted judgements:**

- Success criteria mention reading state "from the service" and comparing digests.
  The generic template calls that too technical. The constitution overrides it:
  criteria must be verifiable by a command or an observable outcome, and this
  repository has already been bitten by criteria abstract enough to pass without
  the objective being met.
- Whether the batch endpoint is declared in the infrastructure template or
  applied as a workload definition is deliberately absent. That is a *how*, and
  belongs to the plan. It carries a scheduling consequence — the template path
  needs a gated deployment the author must approve — which the plan must surface.

**Result**: all items pass on iteration 1 after the three fixes above. Ready for
`/speckit-plan`.
