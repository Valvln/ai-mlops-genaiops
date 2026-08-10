# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repository is

Hands-on preparation for **Microsoft AI-300 — Operationalizing Machine Learning
and Generative AI Solutions**. Exam topics are built as working, verifiable
artifacts rather than read about. Everything runs on an Azure free trial, so
cost is a design constraint rather than an afterthought.

The author is preparing for the exam. Explaining *why* a choice was made is part
of the deliverable, not padding — a change that works but teaches nothing has
missed the point.

## The constitution is binding

`.specify/memory/constitution.md` governs this repository. **Read it before
proposing changes.** Where a principle and a convenience conflict, the principle
wins. The four that come up most:

- **Cost discipline (non-negotiable)** — state up front whether work runs
  locally (free) or requires Azure. Flag anything that could add cost *before*
  implementing, with an estimate. Always propose the cheapest SKU suitable for
  learning. Never leave compute or endpoints running.
- **Commit authorization (non-negotiable)** — never commit or push
  automatically. Show a diff, propose the command, let the author run it. One
  logical change per commit.
- **Validation before commit** — no IaC or CI change is proposed for commit
  until its validation passes (`az bicep build` for Bicep, a green run for CI).
  A change that cannot be validated is reported as unvalidated, never as
  verified.
- **English only** — code comments, documentation, specifications, and commit
  messages are written in English, regardless of the conversation language.
  Conversation with the author is often in Italian; the artifacts are not.

## Spec-driven workflow

Work follows **specify → plan → tasks → implement**, via Spec Kit skills
(`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`).
Feature artifacts live in `specs/<NNN>-<slug>/`.

- A spec states objective, requirements, and success criteria **before**
  implementation. Success criteria must be verifiable by a command or an
  observable outcome, never by opinion.
- Keep the levels separate: the spec says *what* and *why*; the plan says *how*
  (API versions, schema, file layout). Resource names in a spec are a level
  error.
- The Spec Kit `git` extension is installed. Its `before_specify` hook creates
  the feature branch automatically. Its auto-commit hooks are all `optional:
  true` and `git-config.yml` ships with `auto_commit.default` set to `false` —
  **leave it that way**, it is what keeps the tooling compliant with the
  commit-authorization principle.
- Not every task needs a spec. Executing an existing runbook is execution, not a
  feature. Reach for Spec Kit when a new artifact is being built.

## Repository layout

| Path | Scope |
| --- | --- |
| `infra/` | Bicep templates and the deployment runbook |
| `mlops/` | Classical ML operationalization |
| `genaiops/` | Generative AI operationalization |
| `qa-observability/` | Quality assurance, monitoring, observability |
| `rag-optimization/` | Retrieval-augmented generation work |
| `docs/exam-notes/` | AI-300 study notes |
| `specs/` | Spec Kit feature artifacts |
| `.specify/` | Spec Kit configuration, templates, extensions |

New work goes in the folder matching its topic. Propose a new top-level folder
only when none fits.

## Environment

- **`az` and `gh` need a PATH export** before use, or they appear uninstalled:

  ```bash
  export PATH="/usr/local/bin:$PATH"
  ```

- Azure region: use **`northeurope`**. `westeurope` rejects this subscription
  with `RequestDisallowedByAzure` — it is not accepting new customers.
- Generated artifacts are never tracked: `infra/*.json` are build outputs, the
  `.bicep` files are the source of truth.
- **`gh` needs `-R Valvln/ai-mlops-genaiops`.** There are two remotes — `origin`
  (public) and `study` (private) — so `gh` refuses to guess. Getting this wrong
  is how study material or secrets reach the wrong repository.

## Before touching Azure

`infra/DEPLOY.md` is the deployment runbook, written before the first
deployment and revised with observed values afterwards. Read it before running
anything against a subscription. Two things it records that are easy to walk
into:

- **The Key Vault name is locked for 90 days after any teardown.** Purge
  protection is enabled and irreversible, and resource names derive from
  `uniqueString(resourceGroup().id)` — so recreating a resource group with the
  same name collides with the soft-deleted vault.
- **`az bicep build` proves the template compiles, not that it deploys.** Region
  eligibility and resource-name length limits are invisible to it. Only
  `az deployment group what-if` against the live subscription catches them.
- **CI deploys `main.bicep` now, through an approval gate.** A push to `main`
  touching `infra/**` starts `infra-deploy.yml`, which waits for a human
  approval. Never approve a deployment gate on the author's behalf — the gate
  exists to put a human decision in front of every deploy.
- **The CI role permits a fixed set of operations.** Adding a resource type to
  `main.bicep` **will** fail the next deployment with `AuthorizationFailed`.
  That is designed behaviour, not a defect: add the operation the error names to
  `infra/ci-identity.bicep` with the failing run as its provenance. Never widen
  it with a built-in role. See `infra/DEPLOY.md` § 5.
- **A failing `az` command may never have reached Azure.** The CLI resolves the
  subscription from a local account cache first. `No subscriptions found` and
  `Subscription not found` are client-side, and are not authorization refusals.

## Personal study material

Files matching `*.local.md` are the author's own study material — flashcards, an
exam progress tracker — and are gitignored on purpose.

- `tracker_ai300.local.md`, if present, holds the exam timeline, simulation
  results, and which domains are weak. **Read it at the start of a session** to
  understand where the project stands; it is not loaded automatically.
- `FLASHCARDS.local.md` accumulates question/answer recall material per session.
- These files are written in **Italian**, unlike repository artifacts. They are
  study aids, not repository documentation.
- Keep them free of anything derivable from the repo itself. Build state,
  resource counts, and what exists belong to `README.md`, `specs/`, and git
  history — duplicating them there is how the tracker drifts out of date.

## Reporting work

- Report outcomes faithfully. If a build emitted a warning, say so rather than
  calling it clean. If a step was skipped, say which.
- Distinguish *validated to compile* from *verified to work*. The difference has
  already cost this project two latent defects that passed CI.
- `README.md` is the author's own first-person account. Claude may draft
  candidate text; the author reviews, rewrites, and commits it.
