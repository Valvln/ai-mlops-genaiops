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

**Clarifications resolved (2026-08-09)** — both were scope-level, both were
answered toward the narrower option:

- **FR-004** — trust binds to a named approval gate, not to a branch. Adds
  FR-004a (the gate must require a human decision) and a third refusal to SC-004.
- **FR-006** — authority restricted to the resource types the template declares,
  not a predefined general-management role. Adds FR-006a (the operation set is
  discovered, not assumed) and FR-006b, and a fourth refusal to SC-003 on the
  second axis of the boundary: inside the scope, outside the authority.

### Two limits recorded rather than hidden

**SC-005 is weaker than it reads.** It settles fork behaviour from what the
repository observably runs for a pull request, plus the authentication refusals
in SC-004 — not from a genuine fork pull request authored by a second account.
Recorded in Assumptions.

**The approval gate is not a separation of duties.** With one author, the person
approving is the person who wrote the change. The spec says so in Edge Cases and
in Assumptions, and claims only the weaker property: a deliberate pause.

### Watch during planning

FR-006a says the permitted operation set is discovered by deploying and reading
which operation each failure names. This means the plan must expect a sequence of
**failing** deployments before a green one, and must not treat the first failure
as a defect. A plan that pre-computes the operation list from documentation would
satisfy FR-006 in form while abandoning FR-006a and FR-008 — the same shape of
mistake as 002's SC-003.
