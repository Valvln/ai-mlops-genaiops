# ai-mlops-genaiops Constitution

Hands-on portfolio and certification-prep repository for Microsoft **AI-300 —
Operationalizing Machine Learning and Generative AI Solutions**. Every exercise
here is built to be reproducible, cheap to run, and explainable to a reader who
was not present when it was written.

## Core Principles

### I. Cost Discipline (NON-NEGOTIABLE)

This repository is developed on a **Pay-As-You-Go** subscription whose spending
limit is **Off** (verified 2026-08-11 against ARM; see
`docs/exam-notes/compute-cost-model.md` § 1). Nothing caps spend automatically —
a budget alert emails, it does not stop anything. Cost is a hard design
constraint, not an afterthought.

- Every exercise MUST state up front whether it runs **locally (free)** or
  **requires Azure**.
- Any Azure-touching change that could add cost MUST be flagged explicitly
  **before** implementation, together with a rough cost estimate.
- Always propose the cheapest SKU/tier suitable for learning. A production-tier
  default is never acceptable without an explicit, justified decision.
- Provisioned compute and endpoints MUST never be left running unattended.

### II. Version Control Hygiene

Only source-of-truth files are tracked in git.

- Track the source (e.g. `infra/main.bicep`); never commit generated or derived
  artifacts (compiled ARM JSON, build outputs). These MUST be listed in
  `.gitignore`.
- API versions and resource type references MUST be verified against current
  documentation. They are never assumed from memory or copied from an example of
  unknown age.

### III. Commit Authorization (NON-NEGOTIABLE)

Commits and pushes are never performed automatically.

- Every commit MUST be explicitly reviewed and authorized by the project author
  in the current session.
- One logical change per commit. Unrelated changes MUST NOT be batched together.
- A diff is shown and reviewed before a commit is proposed.

### IV. Documentation Ownership

`README.md` is the author's own account, not a machine-generated log.

- After each completed section or milestone, `README.md` MUST be updated, written
  in the **first person** from the project author's perspective.
- It describes what was built, why, and how the Claude Code / spec-driven
  workflow was actively directed by the author.
- It MUST read as the author's engineering decisions, not as a changelog of AI
  actions.
- Claude Code MAY draft candidate text; the author reviews and edits it before it
  is committed.

### V. Validation Before Commit

No infrastructure-as-code or CI change is proposed for commit until its
validation step passes — for example `az bicep build` for Bicep templates, or a
green workflow run for CI changes. A change that cannot currently be validated
MUST be reported as unvalidated rather than presented as verified.

### VI. English Only

From this point forward, all code comments, documentation, specifications, and
commit messages are written in English.

### VII. Folder Structure

New work goes into the folder that matches its topic. A new top-level folder is
proposed only when none of the existing ones fits.

## Repository Structure

| Folder              | Scope                                         |
| ------------------- | --------------------------------------------- |
| `infra/`            | Infrastructure as code (Bicep templates)      |
| `mlops/`            | Classical ML operationalization               |
| `genaiops/`         | Generative AI operationalization              |
| `qa-observability/` | Quality assurance, monitoring, observability  |
| `rag-optimization/` | Retrieval-augmented generation work           |
| `docs/exam-notes/`  | AI-300 study notes                            |
| `.specify/`         | Spec Kit specifications, plans, and templates |

## Development Workflow

Work follows the spec-driven loop: **specify → plan → tasks → implement**.

- A spec states its objective, requirements, and success criteria before
  implementation begins.
- Success criteria MUST be verifiable by a command or an observable outcome, not
  by opinion.
- Validation (Principle V) runs before the change is proposed for commit.
- The author authorizes the commit (Principle III).
- Documentation is updated at milestone boundaries (Principle IV).

## Governance

This constitution supersedes other practices in this repository. Where a
principle and a convenience conflict, the principle wins.

- Amendments require explicit approval from the project author and MUST be
  recorded by bumping the version below.
- Versioning is semantic: **MAJOR** for a removed or redefined principle,
  **MINOR** for a new principle or section, **PATCH** for clarifications that do
  not change meaning.
- Any proposed change that violates a principle MUST be surfaced as a violation
  before implementation, not silently worked around.

**Version**: 1.0.1 | **Ratified**: 2026-08-06 | **Last Amended**: 2026-08-15
