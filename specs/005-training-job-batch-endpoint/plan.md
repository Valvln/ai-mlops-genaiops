# Implementation Plan: From a job that runs to a model that answers

**Branch**: `005-training-job-batch-endpoint` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-training-job-batch-endpoint/spec.md`

## Summary

Train a deliberately trivial model on the existing cluster, reading synthetic
data through the existing data store; prove the tracked record is *correct* by
comparing it against a baseline computed locally before the job is submitted;
register the resulting model with a version; and serve it from a batch endpoint
whose predictions are checked against that same baseline.

The technical approach is shaped by three findings rather than by preference:

- **The estimator is chosen for cross-platform determinism, not for pedagogy.**
  A decision tree is fitted by comparison and counting, so it does not inherit
  the difference between Apple's BLAS and the container's. Logistic regression
  would have failed the comparison intermittently, on an axis unrelated to what
  is being tested ([research.md § R4](./research.md)).
- **The load balancer bills per hour of cluster warmth, not per job.** Jobs run
  back to back inside one warm window cost barely more than one job; jobs spread
  across the day pay the warm-window term repeatedly. Submissions are batched
  ([research.md § R10](./research.md)).
- **The batch endpoint is a workload file, not a template resource.** This keeps
  feature 005 free of CI role changes and gated deployments, at the stated cost
  of the endpoint not being reproducible from `main.bicep`
  ([research.md § R7](./research.md)).

## Technical Context

**Language/Version**: Python 3.10 in the job (curated environment); Python 3.10
locally via `uv`, pinned to match

**Primary Dependencies**: scikit-learn 1.5, MLflow with the `azureml-mlflow`
plugin, NumPy, pandas. Remote versions come from the curated environment
`azureml://registries/azureml/environments/sklearn-1.5/versions/52` — Ubuntu
20.04, Python 3.10, scikit-learn 1.5, confirmed the latest version on 2026-08-16

**Storage**: existing credential-less data store over the existing
`training-data` container, addressed as
`azureml://datastores/.../paths/...`, never as a storage URL

**Testing**: comparison against a locally computed baseline recorded before
submission — exact match on the prediction vector, `1e-9` on metrics. There is no
unit-test suite; the verification *is* the comparison

**Target Platform**: Azure ML compute cluster (Linux), `Standard_DS1_v2`,
min 0 / max 2 nodes, idle 120 s

**Project Type**: ML operationalization workload — scripts and YAML workload
definitions under `mlops/`, no application code

**Performance Goals**: none. Training time must be a negligible fraction of
billed time, which is the opposite of a performance goal

**Constraints**: ≈0.17 € estimated for the whole feature; no node allocated at
either phase boundary; Phase 1 closable without Phase 2; no new resource type in
`main.bicep` unless a runtime refusal demands a role assignment

**Scale/Scope**: 2,000 rows × 5 features; two phases across two days; one
training job, one registration, one batch deployment, one scoring job

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this plan satisfies it |
| --- | --- | --- |
| **I. Cost discipline** (non-negotiable) | ✅ Pass | Every task states local-and-free or Azure-and-billed. Per-phase estimate made in advance at the rates measured this morning ([research.md § R10](./research.md)), not at the node rate alone. Cheapest suitable form throughout: existing cluster reused, batch over real-time, no compute instance, no container registry. FR-029 forbids closing either phase with a node allocated |
| **II. Version control hygiene** | ✅ Pass | Source of truth tracked: scripts, workload YAML, pinned dependency spec. Not tracked: the local `.venv` (already gitignored), the generated dataset (a build output of a recorded procedure), downloaded artifacts. The curated environment is pinned to version 52, read from the registry today, never to `latest` |
| **III. Commit authorization** (non-negotiable) | ✅ Pass | No commit or push is performed by this plan. Each task group ends in a proposed commit, one logical change each, for the author to run |
| **IV. Documentation ownership** | ✅ Pass | `README.md` updated at the milestone in the author's first person, drafted for review rather than committed |
| **V. Validation before commit** | ✅ Pass | No Bicep change is planned. **If** R3's refusal materialises, the role assignment added to `main.bicep` is validated with `az bicep build` before it is proposed, and reported as compiled-not-deployed until the gated run succeeds |
| **VI. English only** | ✅ Pass | All artifacts in English |
| **VII. Folder structure** | ✅ Pass | Work lands in `mlops/`, which is the folder for classical ML operationalization. No new top-level folder |

**Additional gates this repository has earned:**

| Gate | Status | Notes |
| --- | --- | --- |
| Never approve the deployment gate on the author's behalf | ✅ | No gated deployment is planned. The one contingency (R3) is flagged as needing the author |
| Never widen the CI role with a built-in role | ✅ | No CI role change planned; the contingency path adds a scoped role assignment, not a built-in role |
| Read the captured error, not the green summary | ✅ | FR-025 requires a refusal be established as server-side before it is treated as one. R1's assertion makes a silently-untracked run fail loudly instead of passing |
| A criterion that passes is not an objective met | ✅ | Every verification compares against a baseline recorded before the thing under test ran |
| Deferred criteria declared in advance | ✅ | SC-007, SC-013, SC-014, with the dates they become readable |

**Result: no violations. Complexity Tracking is therefore omitted.**

### Re-evaluation after Phase 1 design

Three things the design surfaced that the pre-design check could not have seen:

- **Principle I got stronger, not weaker.** The warm-window term in
  [research.md § R10](./research.md) means cost depends on *how the day is
  scheduled*, not only on how many jobs run. Batching submissions into one warm
  window is now a design rule (FR-026) with a number behind it, and the
  single-submission probe-and-train script in
  [contracts/training-run.md](./contracts/training-run.md) is the first
  application of it.
- **Principle V's scope is narrower than it first appeared.** No Bicep change is
  planned, so there is nothing to `az bicep build` on the main path. The
  contingency in R3 is the only route to a template change, and it carries the
  full validation requirement plus a gated run the author must approve.
- **One design decision has an accepted cost, recorded rather than buried.**
  R7 puts the batch endpoint in a workload file, so it is not reproducible from
  `main.bicep`. This is a deliberate trade against schedule risk and against a
  template that would have to carry a runtime-produced model version. It is not a
  constitution violation — the constitution requires that *source of truth* be
  tracked, and the workload YAML is tracked — but it is the kind of omission that
  should be a decision, so it is written down as one.

**No new violations. The gate passes after design as it did before.**

## Project Structure

### Documentation (this feature)

```text
specs/005-training-job-batch-endpoint/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and predictions
├── data-model.md        # Phase 1 output — entities and their contracts
├── quickstart.md        # Phase 1 output — the runnable validation path
├── contracts/
│   ├── training-run.md      # What the job must record, and what proves it
│   └── batch-scoring.md     # The scoring interface and its verification
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
├── results.md           # Written during implementation, not now
└── tasks.md             # Created by /speckit-tasks, not by this command
```

### Source code (repository root)

```text
mlops/
├── datastore-check/          # Feature 004, unchanged
│   ├── job.yml
│   ├── check_datastore.py
│   ├── sample.csv
│   └── README.md
└── training-pipeline/        # This feature
    ├── README.md             # What was built, and the observed values
    ├── pyproject.toml        # Pinned local baseline environment (uv)
    ├── generate_data.py      # Synthetic data, fixed seed, recorded procedure
    ├── train.py              # Runs on the cluster: probes, trains, tracks, logs the model
    ├── baseline.py           # Runs locally: same data, same seed, no MLflow
    ├── compare.py            # Baseline vs tracked run — the criterion, as code
    ├── train-job.yml         # Phase 1 workload definition
    ├── batch-endpoint.yml    # Phase 2 endpoint
    ├── batch-deployment.yml  # Phase 2 deployment, names the registered version
    └── scoring-input/        # Prepared inputs with differing correct predictions

infra/
└── main.bicep                # Touched ONLY if R3's refusal materialises
```

**Structure Decision**: one new directory, `mlops/training-pipeline/`, holding
both the local baseline tooling and the remote workload definitions. They are
kept together deliberately: the local baseline and the remote job must read the
same generator and agree on the same split, and separating them across
directories is how they drift apart. `mlops/datastore-check/` is not modified —
feature 004's artifact stays as its record.

## Phasing

The two phases are a scheduling boundary with a technical guarantee behind it.

### Phase 1 — 2026-08-16 · training job and its record

Ends with a verified model artifact **already downloaded to disk**. That is what
makes Phase 2 startable from a verified input rather than from a re-run: if
Phase 1 overruns and Phase 2 slips a day, nothing has to be recomputed and no
node is left allocated.

Local and free: dataset generation, baseline computation, script authoring.
Azure and billed: the upload (negligible) and the training job.

### Phase 2 — 2026-08-17 · registry and batch endpoint

Opens with the deferred readings from Phase 1 (SC-007, SC-013), because they
are the only work in this feature that expires — the cost window for 2026-08-16
is readable on 2026-08-17 and its interpretation depends on job timestamps
collected the day before.

Registration is metadata and costs nothing. The scoring job is the only billed
work.

## Risks, and what each one would look like

| Risk | First sign | Response |
| --- | --- | --- |
| MLflow tracks to the node's local filesystem | R1's assertion fails the job in its first seconds | The job declares the tracking URI explicitly; one resubmission |
| `azureml-mlflow` missing from the curated image | Version banner printed by the job shows it absent | Job gains a pip layer; one resubmission (≈0.03 €) |
| Compute identity refused when writing the artifact | Server-side refusal at artifact upload | Role assignment in `main.bicep`, gated deploy the author approves — the one contingency that puts a gated run on the schedule |
| Metrics disagree beyond tolerance | `compare.py` exits non-zero | Recorded as a finding and investigated. **The tolerance is not widened** (FR-016). First suspects: the patch version printed by the job, then whether the job read the intended bytes |
| Batch endpoint identity cannot write output | Scoring job fails after the model loads | Same discovery loop as R3 |
| Phase 1 overruns | Wall clock | Phase 1 closes on its own exit criteria; Phase 2 slips. The downloaded artifact means nothing is lost |

## Complexity Tracking

Not applicable — the Constitution Check records no violations.
