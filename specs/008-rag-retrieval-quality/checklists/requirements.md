# Specification Quality Checklist: Block 5 — RAG Retrieval Quality, Measured

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — *with two declared exceptions, see Notes*
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

## Constitution Compliance (project-specific)

- [x] **Cost Discipline (I)** — every resource appears in the Cost section with its
      daily rate and deletion command before creation (FR-019); the cheapest
      suitable tier is mandated and cannot be raised by a later step (FR-005);
      two success criteria are about cost (SC-010, SC-011)
- [x] **Commit Authorization (III)** — `auto_commit.default` remains `false`; no
      commit is performed by tooling
- [x] **Validation Before Commit (V)** — FR-017 requires two consecutive
      deployments, distinguishing *compiles* from *deploys*
- [x] **English Only (VI)** — the specification is in English
- [x] **Sourced Research Before the Plan Freezes (1.1.0)** — six notes exist in
      `docs/exam-notes/`, dated 2026-08-27 with sources, committed before this
      spec was written; FR-024 and SC-012 close the loop by requiring each note to
      gain either a verification or a finding

## Notes

**Two declared exceptions to "no implementation details", both deliberate:**

1. **Service tier and pricing appear in the spec body.** Constitution Principle I
   makes cost a hard design constraint that must be stated *before*
   implementation, and a tier is the unit in which this service's cost is
   expressed. Removing it to satisfy the generic rule would remove the constraint
   that shapes the entire feature. The tier is stated as a bound, not as a
   configuration.

2. **`infra/foundry.bicep` is named in User Story 3 and FR-015 to FR-018.** The
   story is the settlement of a debt in a specific existing file; there is no way
   to state it without naming it. This is a spec about an existing artifact, not
   about an abstraction.

**Region and embedding model** are confined to the Assumptions section, which the
template designates for documented defaults. Neither appears in a requirement or
a success criterion. FR-004 deliberately states the *constraint* (verify semantic
ranking is available before creating the one service the subscription allows)
rather than the region that satisfies it.

**No resource names appear anywhere in the spec**, per the repository's rule that
resource names in a spec are a level error. The Cost section uses `<service>` and
`<rg>` placeholders.

**One risk carried into planning, not resolved here**: FR-004's regional check is
sequenced before service creation because the Free tier permits one service per
subscription, making a wrong region costly to undo. The plan must not reorder it.
