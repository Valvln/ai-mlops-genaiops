# Feature Specification: From a job that runs to a model that answers

**Feature Branch**: `005-training-job-batch-endpoint`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "The rest of the Domain 2 backbone — a training job
that runs on the existing cluster and reads from the existing data store, tracked
so its record can be trusted, the resulting model registered with a version, and
served by a batch endpoint. A trivial model on synthetic data: the point is the
mechanics of tracking, registration and serving, not accuracy. One feature across
two days, in two phases, and the first phase must be able to close on its own."

## Context

Feature 004 gave the workspace somewhere to read from and something to run on,
and proved both by observation. Nothing has yet *used* them for their purpose.
The verification job it ran computed a checksum — enough to prove a file was
read, and deliberately not a model. This feature closes the gap between an
environment that could train a model and one that has.

It is the last construction feature of week 2. Four things shape it, and each
produces requirements below.

### The scope is a backbone, and the cuts are already paid for

Week 2 covers the heaviest domain of the exam against four working days instead
of seven. The decision recorded before this feature opened was to build one
complete path — **data store → training job → registered model → batch
endpoint** — rather than to touch fifteen topics shallowly. Automated model
selection, hyperparameter search, distributed training and real-time endpoints
are cut from construction and remain exam material. They are not reopened here.

The model itself is deliberately trivial. A feature that spent its budget on
accuracy would have bought the one thing the exam does not ask for.

### Two phases, and the first must survive the second not happening

The work is split across two days. **Phase 1** is the training job and its
record; **Phase 2** is registration and serving. If Phase 1 overruns, it closes
anyway and Phase 2 slips to the next available session.

That is a requirement on how Phase 1 is built, not just on how it is scheduled:
it must not leave a job half-defined, a node allocated, or a model that exists
only inside a run that nothing can retrieve it from. A phase that can only be
closed by finishing the next one is not a phase.

### The numbers this feature consumes rather than rediscovers

The compute cost model was re-measured on 2026-08-16 against the first real
billing day, and `docs/exam-notes/compute-cost-model.md` § 7.2 now records
figures this specification treats as inputs:

- **Billing runs from node allocation, not from script start.** Measured: 25.0
  minutes billed against 12.6 minutes of script time across three jobs — 1.98×.
  Provisioning, image pull and the idle tail before scale-down are all billed.
  **A short job costs about twice what its script costs**, which makes "run it
  again to see" an expensive habit and makes batching work into fewer, longer
  jobs a design constraint rather than an optimisation.
- **The node rate is not the whole rate.** The virtual-machine meter was 26% of
  the first billing day. Adding the node's operating-system disk gives ≈0.082 €
  per node-hour; a load balancer and a static public IP add ≈0.025 € per hour
  that the cluster stays warm, on a tail of roughly two hours after the last
  node is released.
- **A load balancer is billed for a resource that is not visible in the resource
  group.** Feature 004 checked for network resources, found none, and inferred
  no charge. The check was right; the inference was wrong. Existence and billing
  are different ledgers.
- **Cost data lags ingestion by roughly 8 to 24 hours.** A day's spend cannot be
  verified on the day it is spent.

Feature 004 also settled which identity's grants matter: a job declaring managed
identity runs as the **compute's** identity, not the workspace's, and a grant
held by one principal does not authorise a read performed by another. That
identity currently holds exactly one data-plane grant. This feature asks it to do
more than read one container, so a refusal is an expected event rather than a
surprise — see FR-020.

### A criterion that passes is not an objective that is met

The repository's most expensive recurring defect, and the one this feature is
most exposed to, because every step of it has a cheap check that measures the
wrong thing:

| The cheap check | What it actually proves |
| --- | --- |
| The job finished successfully | A process exited zero |
| The run appears in the tracking interface | A record was created |
| The run shows metrics | Numbers were written, not that they are the right numbers |
| An artifact is attached to the run | A file was uploaded, not that it is a loadable model |
| The model appears in the registry | An entry exists, not that it is versioned or retrievable |
| The scoring job completed | Compute ran, not that predictions are correct |

Every success criterion below is written against the right-hand column. The
mechanism throughout is the same one feature 004 used for the data store: an
independently computed baseline, established **before** the thing under test
runs, that the result must match.

## Clarifications

### Session 2026-08-16

- Q: How is "the tracked metrics are correct" proven? → A: **by computing the
  same metrics locally, on the same bytes, with the same seed, and requiring the
  tracked values to match within a stated tolerance.** A run visible in the
  interface proves a record exists. Metrics displayed in that record prove
  numbers were written. Neither distinguishes a correct training run from one
  that trained on the wrong column, dropped rows at the mount, or logged a
  constant. Only a value computed independently can disagree, and a check that
  cannot disagree is not a check.
- Q: Where does the training data come from, given the objective requires the job
  to read the data store? → A: **synthetic data generated locally by a recorded
  procedure with a fixed seed, uploaded to the existing container, and read by
  the job through the existing data store.** Generating it inside the job would
  be cheaper and would remove the data store from the path the feature exists to
  exercise. The fixed seed is what makes the local baseline comparable to the
  remote run at all — without it there is no shared ground truth. The file that
  feature 004 uploaded is five rows and cannot train anything.
- Q: Is the job's cost part of Phase 1's exit, given cost data lags a day? → A:
  **split.** Phase 1 closes on **billable node time derived from the job's own
  allocation timestamps**, converted to an expected charge at the measured rate —
  available immediately and sufficient to detect a node left running. The
  **measured** figure is declared deferred to the next day. Feature 004 scheduled
  a cost verification for the day of the spend and could not close it; the same
  criterion is not written the same way twice.
- Q: Does proving "the model is versioned" require more than reading a version
  field? → A: **yes, and it is free.** Registration is metadata over an artifact
  that already exists, so registering a second time costs nothing and is the only
  thing that distinguishes a registry that versions from a field that happens to
  contain `1`.

## Cost

**Both phases provision compute by the hour.** Stated up front, per constitution
principle I. No new billable resource type is introduced: the cluster and the
data store already exist, and a batch endpoint holds no compute between jobs.

Estimated from the rates measured on 2026-08-16, which supersede the
node-rate-only arithmetic used before:

| Work | Expected charge |
| --- | --- |
| Phase 1 — training job, allowing for two or three cluster activations | **≈0.10 €** |
| Phase 2 — registration (free, metadata) plus one or two scoring runs | **≈0.08 €** |
| Whole feature, start to close | **well under 0.50 €** |

Three mechanisms hold that estimate, and each is a requirement rather than a
hope:

- Work is batched into **as few cluster activations as practical** (FR-023).
  Because billing starts at allocation, five short diagnostic runs cost more than
  one job that logs everything the first time.
- The endpoint chosen is a **batch** endpoint (FR-017). It bills only while a
  scoring job runs. A real-time deployment bills for as long as it exists, which
  is the failure mode a two-day feature is most likely to leave behind.
- **Neither phase closes with a node allocated or an endpoint holding compute**
  (FR-025), verified by reading the service rather than by trusting a
  scale-down interval to have elapsed.

One cost remains **unknown and will be measured**: whether the load balancer
identified on 2026-08-16 is billed while the cluster is at rest, or only while it
is warm. The evidence so far points at "only while warm" — it was torn down after
roughly two hours rather than running to the end of the day — but that is an
inference from an assumed rate, and this repository has already been wrong about
this exact meter once. See FR-028 and SC-013.

## Deferred criteria

Declared here rather than discovered at closing time, because feature 004 closed
with a criterion that could not be read on the day it was scheduled.

| Criterion | Depends on | Readable from |
| --- | --- | --- |
| SC-007 — measured cost of Phase 1 | Cost data for 2026-08-16 | 2026-08-17 |
| SC-013 — load balancer at rest | Cost data for 2026-08-16 | 2026-08-17 |
| SC-014 — measured cost of the whole feature | Cost data for 2026-08-17 | 2026-08-18 |

**SC-013 carries over from feature 004 and its test has to change.** That feature
planned a binary reading — a load-balancer row present or absent for a day at
rest. This feature's own training jobs run on 2026-08-16 and put the cluster into
exactly the warm state that produces such a row, so presence no longer
discriminates. The replacement is quantitative and is stated in FR-028.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A training run happened, and its record can be trusted (Priority: P1)

The author needs a model trained on the cluster, reading real data through the
data store, with a record of how it was trained that is accurate enough to act
on. The value is not the model. It is that the recorded parameters and metrics
describe what actually happened, because every later step — comparing runs,
choosing a version to deploy, explaining a regression — reads that record and
inherits its errors.

**Why this priority**: This is the whole of Phase 1 and the foundation of
everything after it. A registry entry pointing at a run whose metrics are wrong
is worse than no registry entry, because it is trusted.

**Independent Test**: Fully testable by submitting the job and comparing the
recorded parameters and metrics against values computed locally on the same
bytes with the same seed. Delivers the Domain 2 tracking objective on its own,
with no registration and no endpoint in existence.

**Acceptance Scenarios**:

1. **Given** synthetic data of known content in the container and a locally
   computed baseline recorded before submission, **When** the job runs on the
   cluster and completes, **Then** every metric in the run's record matches the
   baseline within the stated tolerance.
2. **Given** a completed run, **When** its recorded parameters are read, **Then**
   they state the seed, the dataset identity and the model configuration actually
   used, and not defaults the script never applied.
3. **Given** the workspace's tracking configuration is not known in advance,
   **When** the job runs, **Then** whether the destination was configured by the
   workspace or declared by the job is settled by observation and written down
   with the evidence that settled it.
4. **Given** a metric that disagrees with the baseline beyond tolerance,
   **When** the comparison is made, **Then** the disagreement is recorded as a
   finding and investigated, and is not absorbed by widening the tolerance.

---

### User Story 2 - The trained model can be got back out (Priority: P1)

The author needs the artifact the run produced to be retrievable and usable, not
merely attached. A model that cannot be loaded is a file.

**Why this priority**: It completes Phase 1's exit and is the precondition for
Phase 2. It is also the step where "an artifact exists" is most likely to be
mistaken for "a model exists", because both look identical in a listing.

**Independent Test**: Fully testable by retrieving the artifact from the run,
loading it locally, and scoring the same inputs the baseline used. Delivers a
downloadable, verified model with no registry and no endpoint involved.

**Acceptance Scenarios**:

1. **Given** a completed run with an attached model artifact, **When** the
   artifact is retrieved and loaded, **Then** it produces predictions identical
   to the local baseline's predictions on the same inputs.
2. **Given** the author holds no data-plane role on the storage account,
   **When** retrieval is attempted, **Then** either it succeeds by a path that is
   recorded, or the refusal is identified as a refusal and resolved by FR-020
   rather than worked around silently.

---

### User Story 3 - The model is registered, and the registry actually versions (Priority: P2)

The author needs the model to exist as a named, versioned entity that is
traceable back to the run that produced it, so that a deployment can name a
version rather than a file path.

**Why this priority**: First step of Phase 2. Free in compute, and it is what
turns a run artifact into something an endpoint can refer to.

**Independent Test**: Fully testable by registering, reading back the entry, and
registering a second time to observe the version change. Delivers the model
registry objective with no endpoint in existence.

**Acceptance Scenarios**:

1. **Given** a verified model artifact from a completed run, **When** it is
   registered, **Then** the registry holds an entry carrying a name, a version,
   and a reference identifying the run it came from.
2. **Given** an existing registered version, **When** the same model is
   registered again under the same name, **Then** a distinct higher version is
   created and the earlier version remains retrievable.

---

### User Story 4 - The model answers questions in bulk, and the answers are right (Priority: P2)

The author needs the registered model served in the form that suits scoring a
file of inputs — compute that appears when a scoring job is submitted and
disappears when it ends — and needs the predictions it returns to be the model's
own.

**Why this priority**: Completes the backbone and the Domain 2 serving
objective. Batch rather than real-time is a cost decision already taken: batch
pays only during the job.

**Independent Test**: Fully testable by submitting a prepared input set and
comparing returned predictions against predictions computed locally from the
same registered version.

**Acceptance Scenarios**:

1. **Given** a registered model version and a prepared input set of known
   content, **When** a scoring job is submitted to the batch endpoint and
   completes, **Then** the returned predictions match, row for row, predictions
   computed locally from the same registered version on the same inputs.
2. **Given** a completed scoring job, **When** the compute is read from the
   service afterwards, **Then** it holds zero nodes, without an operator command
   having caused it.
3. **Given** the feature is being closed, **When** endpoints and compute are
   read, **Then** no real-time endpoint exists, and no endpoint holds allocated
   compute.

---

### User Story 5 - Two cost questions are answered by measurement, not by argument (Priority: P3)

The author needs the carried-over load-balancer question settled, and this
feature's own spend measured, on the first day the data supporting each exists.

**Why this priority**: It changes the shutdown procedure for the rest of the
project — if a resting cluster bills, the cluster must be deleted at the end of
each week rather than left. It is P3 only because it cannot be done earlier, not
because it matters less.

**Independent Test**: Fully testable by a cost reading, independent of every
other story.

**Acceptance Scenarios**:

1. **Given** cost data for a day on which the cluster was warm for a known
   window, **When** the load-balancer meter is divided by its rate, **Then** the
   implied duration is compared against the known warm window and against a full
   day, and the comparison — not the presence of the row — decides the answer.
2. **Given** an estimate made before the work and a measurement made after,
   **When** they disagree, **Then** the disagreement is recorded as a result with
   its likely cause, and the estimate is not retrospectively adjusted to match.

### Edge Cases

- **The metrics match the baseline for the wrong reason.** If the job silently
  trained on locally generated data rather than on the mounted file, the
  comparison would pass. The mount path and a digest of the bytes the job
  actually read must be recorded by the run, as feature 004 did, so that "same
  numbers" is backed by "same bytes".
- **The tracking destination is configured but writes nowhere useful.** A run can
  be created against a local file store on the node and vanish with the node. The
  criterion is that the record is readable from the workspace *after* the node is
  released.
- **The compute identity is refused when writing.** It currently holds one
  read grant on one container. Writing a model artifact or a tracking record may
  be refused. This is an expected discovery, not a defect, and is resolved by
  FR-020.
- **A refusal is mistaken for a failure.** A command that never reached the
  service, an empty result, and an authorisation denial look similar at the exit
  code. The class of failure must be established from a server-side response
  before it is treated as a permissions problem.
- **The registered model cannot be deployed because the endpoint's identity
  cannot read it.** The endpoint runs as its own principal, which is a different
  principal again from the compute's. Feature 004's rule applies unchanged.
- **Phase 1 overruns.** The job must be left in a closable state: no allocated
  node, no half-written definition, and the model artifact already retrieved and
  verified, so that Phase 2 can start from a verified input rather than re-run
  Phase 1.
- **The scoring input is trivially separable.** If every prediction is the same
  class, a comparison against the baseline passes even if the model was never
  loaded. The input set must contain rows whose predicted classes differ.

## Requirements *(mandatory)*

### Functional Requirements

**Data**

- **FR-001**: The training data MUST be synthetic and generated by a recorded
  procedure with a fixed seed, so that identical bytes can be reproduced without
  reference to the copy stored remotely.
- **FR-002**: The job MUST obtain its training data by reading it through the
  existing data store. It MUST NOT generate the data inside the job, and MUST NOT
  embed it in the training script.
- **FR-003**: The dataset MUST be large enough that evaluation metrics are
  non-degenerate and discriminating, and small enough that training time is a
  negligible fraction of the job's billed time.
- **FR-004**: The job MUST record evidence that it read the intended bytes — the
  path it read from and a digest of the content — so that agreement with the
  local baseline cannot be produced by data the job supplied to itself.

**The training job**

- **FR-005**: The job MUST run on the compute cluster that already exists. It
  MUST NOT create a new compute target and MUST NOT run the training locally as
  a substitute.
- **FR-006**: The job MUST run under the compute's managed identity, which
  feature 004 established is the identity whose grants determine what a job may
  read.
- **FR-007**: The estimator MUST be a simple supervised model whose training is
  deterministic given the data and a fixed seed. Predictive accuracy is
  explicitly not an objective.
- **FR-008**: The feature MUST NOT use automated model selection, hyperparameter
  search, or distributed training.

**Tracking**

- **FR-009**: Whether the run's tracking destination is configured by the
  workspace or must be declared by the job MUST be settled by observation and
  recorded with the evidence that settled it. It MUST NOT be assumed in either
  direction.
- **FR-010**: The run MUST record the parameters that determined training —
  including the seed and the identity of the dataset — and at least two
  evaluation metrics.
- **FR-011**: The run MUST record the trained model as an artifact that can be
  retrieved after the compute node has been released.
- **FR-012**: The recorded run MUST be readable from the workspace after the node
  that produced it has been released.

**Verification**

- **FR-013**: A baseline MUST be computed locally, on the same bytes and with the
  same seed, and recorded **before** the job is submitted.
- **FR-014**: Evidence that tracking is correct MUST be agreement between the
  recorded metrics and that baseline, within a numeric tolerance stated in
  advance. The run's appearance in any interface MUST NOT be offered as evidence.
- **FR-015**: Evidence that the artifact is a usable model MUST be that it is
  retrieved, loaded, and reproduces the baseline's predictions. The presence of a
  file MUST NOT be offered as evidence.
- **FR-016**: If a comparison disagrees beyond the stated tolerance, the
  disagreement MUST be recorded and investigated. The tolerance MUST NOT be
  widened to accommodate it.

**Registration**

- **FR-017**: The verified model MUST be registered as a named entity carrying a
  version and a reference to the run that produced it.
- **FR-018**: That the registry versions MUST be demonstrated by registering a
  second time and observing a distinct higher version, with the earlier version
  still retrievable. Reading a version field MUST NOT be offered as evidence.

**Serving**

- **FR-019**: The registered model MUST be served by a batch endpoint. A
  real-time endpoint MUST NOT be created at any point in this feature.
- **FR-020**: The batch deployment MUST run on the compute cluster that already
  exists.
- **FR-021**: Evidence of serving MUST be predictions returned for a prepared
  input set, matching row for row against predictions computed locally from the
  same registered version. A scoring job reaching a completed state MUST NOT be
  offered as evidence.
- **FR-022**: The prepared input set MUST contain rows whose correct predictions
  differ, so that a constant output cannot satisfy FR-021.

**Authority**

- **FR-023**: When an identity is refused an access this feature needs, the
  refusal MUST be resolved by granting exactly the access the refusal names, to
  the principal the refusal names. A predefined role MUST NOT be assigned, and no
  grant may be widened beyond the named operation and scope.
- **FR-024**: Every grant or deployment operation added MUST record the
  identifier of the run or job whose failure demanded it.
- **FR-025**: Before a failure is treated as a missing permission, it MUST be
  established as a server-side refusal and distinguished from a client-side
  failure, a wrong path, and an empty result.

**Cost and closure**

- **FR-026**: Work MUST be batched into as few cluster activations as practical.
  Because billing runs from allocation, a script MUST log everything a diagnosis
  would need on its first run rather than rely on resubmission.
- **FR-027**: Each phase MUST have its charge estimated before its work, at the
  measured rate, and measured afterwards on the first day the data exists.
- **FR-028**: The carried-over question of whether a resting cluster bills a
  load balancer MUST be settled quantitatively: the meter divided by its rate,
  the implied duration compared against the known warm window and against a full
  day. The presence or absence of the row MUST NOT be used as the test, because
  this feature's own jobs produce that row.
- **FR-029**: Neither phase may close while a node is allocated or an endpoint
  holds compute. Closure MUST be established by reading the service, not by
  assuming an interval has elapsed.
- **FR-030**: Phase 1 MUST be closable independently of Phase 2, leaving no
  allocated node, no partially defined job, and a model artifact already
  retrieved and verified.
- **FR-031**: A criterion depending on data that does not exist on the day of the
  work MUST be declared deferred, with the date it becomes readable, at the time
  the criterion is written.

### Key Entities

- **Training dataset**: synthetic tabular data of known content, generated from a
  fixed seed, held in the existing container and addressed through the existing
  data store. Its identity — content digest and row count — is what makes the
  local baseline and the remote run comparable.
- **Local baseline**: parameters, metrics and predictions computed on the author's
  machine from the same bytes and seed, recorded before the job is submitted. It
  is the only thing in the feature capable of contradicting a tracked result.
- **Training run**: the record produced by the job, holding the parameters, the
  metrics, the evidence of what bytes were read, and the model artifact. Survives
  the compute node that created it.
- **Registered model**: a named entity carrying a version and a reference to the
  run that produced it. The thing a deployment names instead of a file path.
- **Batch endpoint and deployment**: the addressable target for scoring, and the
  configuration binding a registered version to compute. Holds no compute between
  scoring jobs.
- **Scoring input and output**: a prepared set of rows with differing correct
  predictions, and the predictions returned for them — compared against the
  local baseline rather than inspected.

## Success Criteria *(mandatory)*

Each criterion names the phase that owns it. Criteria marked **DEFERRED** cannot
be read on the day their work is done and carry the date they become readable.

### Phase 1 — 2026-08-16

- **SC-001**: A job submitted to the existing cluster reaches a completed state,
  read from the service rather than inferred from a command's exit code.
- **SC-002**: The cluster is observed holding at least one node while the job
  runs, and zero nodes afterwards, with no operator command having caused the
  release.
- **SC-003**: Every parameter and metric in the run's record agrees with the
  locally computed baseline within the tolerance stated before the job was
  submitted, and the run records the path and content digest of the data it read,
  matching the digest recorded before the job existed.
- **SC-004**: The model artifact is retrieved from the run after the node has
  been released, loaded, and reproduces the baseline's predictions on the same
  inputs.
- **SC-005**: Whether the tracking destination is configured by the workspace or
  declared by the job has a written answer, stating the observation that settled
  it and what would have been observed had the answer been the other one.
- **SC-006**: Billable node time for the phase is derived from the job's own
  allocation and release timestamps and converted to an expected charge at the
  measured rate, yielding a figure available the same day.
- **SC-007** *(**DEFERRED** — readable 2026-08-17)*: The measured cost of
  2026-08-16, read from the cost report, agrees with the SC-006 estimate to
  within a factor stated when the estimate is made.
- **SC-008**: At the moment Phase 1 closes, the cluster holds zero nodes, no
  endpoint of any kind exists, and the phase's artifacts are complete enough that
  Phase 2 could begin from them without re-running the job.

### Phase 2 — 2026-08-17

- **SC-009**: The registry holds an entry for the model carrying a name, a
  version, and a reference identifying the run that produced it.
- **SC-010**: Registering the same model a second time produces a distinct higher
  version, and the earlier version is still retrievable afterwards.
- **SC-011**: A scoring job against the batch endpoint returns predictions that
  match, row for row, predictions computed locally from the same registered
  version on the same inputs — and the input set contains rows whose correct
  predictions differ.
- **SC-012**: At the moment the feature closes, no real-time endpoint exists, no
  endpoint holds allocated compute, and the cluster holds zero nodes, each read
  from the service.
- **SC-013** *(**DEFERRED** — readable 2026-08-17, over the 2026-08-16 window)*:
  The load-balancer meter for a day on which the cluster's warm window is known
  is divided by its rate, and the implied duration is compared against that warm
  window and against a full day. The answer is stated with the arithmetic that
  produced it, and either outcome is acceptable.
- **SC-014** *(**DEFERRED** — readable 2026-08-18)*: Cost attributable to the
  whole feature, compared against the idle-day baseline, is under 1 €.

## Assumptions

- The compute cluster and the data store built in feature 004 exist, are
  configured as recorded there, and are not re-investigated. Verified at rest at
  the start of this feature: zero nodes, no endpoints.
- The author holds no data-plane role on the storage account. Uploading the
  training data is therefore setup performed with the account key, not a claim
  under test — how the bytes arrive is not what this feature measures.
- Registration is metadata over an artifact that already exists and consumes no
  compute, which is what makes the second registration in FR-018 free.
- A batch endpoint holds no compute between scoring jobs, so its existence
  between the two phases is not a cost risk. This is the property that selected
  it over a real-time endpoint.
- Cost data continues to lag ingestion by roughly 8 to 24 hours, as measured on
  2026-08-15 and 2026-08-16.
- The load-balancer and public-IP rates used in the § 7.2 arithmetic are list
  prices rather than measured rates. SC-013's conclusion inherits that
  uncertainty and must say so.
- Metrics computed on different machines may differ in the last bits of a
  floating-point value. The tolerance in FR-014 accommodates representation
  noise only; it is not a budget for disagreement.

## Out of Scope

- Automated model selection, hyperparameter search and distributed training —
  cut from construction for week 2, retained as exam material.
- Real-time endpoints and progressive rollout — cut because a real-time
  deployment bills for as long as it exists rather than while it serves, which is
  the wrong risk to carry into a two-day feature. Progressive rollout presupposes
  one.
- Data drift detection, production metric monitoring and retraining triggers —
  deliberately deferred to week 4, where monitoring is the domain rather than a
  digression.
- Model accuracy. The estimator is chosen for determinism and speed. Any
  criterion here that appears to be about model quality is about reproducibility.
- Deleting or recreating the environment. The 90-day name lock on the key vault
  makes teardown a decision for the end of the preparation, not for this feature.
