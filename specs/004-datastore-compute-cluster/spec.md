# Feature Specification: A place to read data from, and a target to run on

**Feature Branch**: `004-datastore-compute-cluster`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "Give the workspace the two things a training job
needs — where it reads its data from, and what it runs on — declared in the
template like everything else. A compute cluster able to carry training jobs and
batch scoring. Zero cost at rest as a verifiable requirement, not an aspiration:
declared with a minimum of zero nodes, and verified at zero *after* the
deployment. The size is chosen against the per-family quota, not only against
the price. The narrow continuous-integration authority is extended by exactly the
operation a failure names, never by a predefined role."

## Context

Features 001 to 003 built a workspace, established what its identity may do, and
put a gated deployment path in front of it. What none of them built is anything
a job could use: the workspace deployed today can hold no data of its own and
run no work. This feature adds the two objects that change that, and it is the
first in this repository that provisions something billed by the hour.

Three things make it different from what came before, and each shapes a
requirement below.

### The first hourly resource, on a subscription with no ceiling

Every previous feature was free by construction. This one is not. The
subscription is Pay-As-You-Go with its spending limit **off**: nothing stops
spend automatically, and the budget alert notifies rather than caps. The
protection against cost here is therefore not a platform control — it is the
shape of the resource itself. A compute cluster that rests at zero nodes costs
nothing while idle *by the platform's documented behaviour*, which is why it is
the form chosen, and why the requirement is not "keep costs low" but "rest at
zero, observed".

### The numbers this feature consumes rather than rediscovers

The compute cost model was measured against this subscription on 2026-08-11 and
recorded in `docs/exam-notes/compute-cost-model.md`. This specification treats
its findings as inputs, not as questions:

- Regional dedicated cluster quota is **20 vCPU**; the relevant per-family
  dedicated limits sit between 6 and 20.
- Regional **low-priority quota is 0**, which gates every per-family
  low-priority reading of `-1`. The standard advice to save money with
  low-priority nodes is unavailable here, and the per-family figure is the wrong
  place to look for that.
- The cheapest size the service offers in this region has a **family quota of
  zero** and is therefore not allocatable. Cheapest-on-the-price-list and
  cheapest-that-can-actually-start are different answers.
- Whether a cluster resting at zero nodes still incurs a load-balancer charge is
  **not stated by the documentation and not verified**. This feature is the
  first opportunity to settle it.

### A criterion that passes is not an objective that is met

This repository has produced that outcome twice — once in feature 002, where a
success criterion about grant scope passed while the authority it existed to
reduce had merely been relocated, and again inside feature 003 in an assertion
written specifically to avoid it. The habit that works is reading the captured
error rather than the green summary, and choosing the axis a check will fail on
*before* writing it.

Two checks in this feature are one careless sentence away from that failure
mode, and both are called out explicitly in the criteria:

- A declaration of zero minimum nodes in the template is **not** evidence that
  the cluster rests at zero. It is evidence of what was requested.
- The existence of a data store record in the workspace is **not** evidence that
  the workspace can read data through it. It is evidence that an object was
  created.

## Clarifications

### Session 2026-08-15

- Q: How is "the data store is reachable from the workspace" proven? → A: **by a
  job, running on the new cluster, that reads a file through the data store and
  produces an output derived from that file's contents.** The two cheaper
  options were both rejected as measuring the wrong thing. Reading the store's
  record proves an object exists. Reading and writing the file from the author's
  own machine proves the author's permissions, not the workspace's — the
  credentials exercised would be the wrong ones, and the claim would be exactly
  one step wider than its evidence. Only a job reads as the identity whose access
  is being asserted. It also costs almost nothing (single-digit node-minutes) and
  buys a second answer for free: allocating the first node is the moment a
  missing authorisation announces itself.
- Q: What is the cluster's maximum node count? → A: **two.** At rest the cost is
  zero either way, so the decision is about what can be demonstrated against what
  a runaway job could cost. Two nodes let a batch deployment distribute
  mini-batches across nodes, which is the behaviour of batch scoring that the
  exam actually asks about; one node would leave that unobservable. The exposure
  it adds is bounded and known: a job left running for a full day costs roughly
  2.77 €, against roughly 1.39 € for a single node. Both sit inside the week's
  budget, and neither is the real risk — the real risk is a job left running,
  which the automatic scale-down addresses regardless of the maximum.

## Cost

**This feature introduces hourly billing to the project.** Stated up front, per
constitution principle I.

| State | Expected charge |
| --- | --- |
| Both objects deployed, no job submitted | **zero** — the data store is metadata over storage already deployed; the cluster holds no allocated nodes |
| The verification job running | the node rate for the job's duration, plus the idle interval before scale-down |
| The whole of this feature, start to close | **well under 1 €**, dominated by a job measured in minutes |

Two mechanisms carry that expectation, and both are requirements rather than
hopes: the cluster rests at a minimum of zero nodes (FR-005), and the idle
interval before it scales back down is declared rather than left to the default
(FR-007). The second is small money — the default tail is roughly two minutes of
node time per job — but it is the mechanism the exam asks about, and a default
that has not been read is not a decision.

Two costs are **excluded by scope, not by hope**: no compute instance is created
(billed roughly 25 €/month while merely stopped, for a disk and a load balancer
that stopping does not release), and no real-time endpoint deployment is created
(billed for as long as it exists, roughly 42 €/month idle). Both are in
`docs/exam-notes/compute-cost-model.md` § 4, and both are cut from construction
in week 2 while remaining exam material.

One cost is **unknown and will be measured** rather than assumed away: whether a
cluster resting at zero nodes still bills a load balancer. FR-016 records it as
an observation with either outcome acceptable. If the answer turns out to be
yes, the cluster becomes an object that must be deleted rather than left, and
that changes the shutdown procedure for the rest of the project.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data has a declared home the workspace can actually read (Priority: P1)

The author declares, in the infrastructure template, a named location where
training data lives. After deployment, a job reads a file from that location and
produces a result derived from the file's contents — proving the path works end
to end, as the workspace's own identity, without any account key existing
anywhere in the declaration.

**Why this priority**: Half the objective. A training job that cannot find its
data has nothing to train on, and this is the half whose verification is easiest
to fake.

**Independent Test**: Deploy the template, place a small file in the declared
location, submit a job that reads it through the data store reference, and
compare the job's output against the file's known contents.

**Acceptance Scenarios**:

1. **Given** the template declares the data store, **When** the deployment
   completes, **Then** the workspace lists a data store of that name that it did
   not create for itself.
2. **Given** a file of known contents placed in the declared location, **When** a
   job reads it through the data store reference, **Then** the job completes and
   its output is derived from the file's contents — a byte count, a checksum, or
   a row count that could not be produced without having read the bytes.
3. **Given** the data store declaration, **When** it is inspected for
   credentials, **Then** it contains no account key and no shared access
   signature: access is by identity.
4. **Given** the job has completed, **When** its logs are read, **Then** they
   contain no authorisation failure against the storage account.

---

### User Story 2 - Compute exists, and costs nothing when nothing is running (Priority: P1)

The author declares a compute cluster in the same template. It can run a job
when a job is submitted. Between jobs, it holds no allocated nodes — and this is
read back from the deployed resource, not assumed from the request that created
it.

**Why this priority**: The other half of the objective, and the half that can
cost money. It is also the half where the tempting check is the worthless one.

**Independent Test**: After deployment, query the deployed cluster's current
node counts from the service. Then submit the verification job, watch the count
rise, and query again after the idle interval has passed.

**Acceptance Scenarios**:

1. **Given** the deployment has completed and no job has been submitted,
   **When** the cluster's state is read from the service, **Then** every node
   count it reports — running, idle, preparing, leaving — is zero.
2. **Given** the cluster at zero nodes, **When** a job is submitted, **Then**
   nodes are allocated and the job runs, demonstrating that zero at rest is not
   zero capability.
3. **Given** the job has finished and the declared idle interval has elapsed,
   **When** the cluster's state is read again, **Then** every node count has
   returned to zero without any manual action.
4. **Given** the chosen node size, **When** it is checked against the
   subscription's quota, **Then** the family it belongs to has a non-zero
   dedicated limit, and the cluster's maximum vCPU demand fits inside both that
   limit and the regional total.
5. **Given** the cluster definition, **When** it is inspected, **Then** it
   requests dedicated nodes and not low-priority nodes, because the regional
   low-priority quota on this subscription is zero and a low-priority request
   could never be satisfied.

---

### User Story 3 - The narrow deployment authority is extended by exactly what a failure names (Priority: P2)

Adding these two objects means the template declares resource types the
continuous-integration role has never been permitted to touch. The deployment
fails, naming an operation. The author adds that operation and no other, records
which run demanded it, and runs again — as many times as it takes.

**Why this priority**: It is the designed behaviour of feature 003's role, and
the first time it fires in anger. It cannot happen before the template changes,
which is why it is not P1.

**Independent Test**: Push the template change, let the gated deployment run,
and read the failure. The operation named in the error is the only thing added.

**Acceptance Scenarios**:

1. **Given** the template declares a resource type the deployment role does not
   permit, **When** the deployment runs, **Then** it fails with an authorisation
   error that names the missing operation.
2. **Given** such a failure, **When** the role is amended, **Then** exactly the
   operation named is added, and the identifier of the failing run is recorded
   alongside it as its provenance.
3. **Given** several such failures in succession, **When** the feature closes,
   **Then** every operation added during it traces to a specific run that
   demanded it, and no operation was added in anticipation of a failure that
   never happened.
4. **Given** the deployment finally succeeds, **When** the role is inspected,
   **Then** it holds no predefined role and no wildcard, and the boundary
   established by feature 003 still refuses the actions it refused before.

---

### User Story 4 - Two open questions are answered by observation, not by argument (Priority: P3)

Two things this project wrote down as unknown become answerable the moment the
first compute exists. The author records what actually happened, whichever way
it went.

**Why this priority**: Neither answer is required for the feature to work. Both
are the reason this is the right moment to ask — the cost of asking later is a
session; the cost of asking now is reading an error that was going to appear
anyway.

**Independent Test**: Create the cluster and see whether anything is refused.
Leave it at rest and read the cost report a day or two later.

**Acceptance Scenarios**:

1. **Given** the workspace was deliberately denied authority over the resource
   group as a whole, **When** the first compute target is created, **Then** the
   outcome is recorded: either it succeeded, and the denied authority is
   demonstrably not needed for this, or it failed with an authorisation error,
   which is recorded verbatim along with what was done about it.
2. **Given** the cluster resting at zero nodes, **When** the cost report is read
   for a period covering at least a full day at rest, **Then** it is recorded
   whether any charge appears that is not node-hours — settling whether a
   load-balancer charge survives at zero nodes.
3. **Given** either observation, **When** it is written down, **Then** it states
   what was observed and on what date, and does not present an expectation as a
   result.

---

### Edge Cases

- **The cluster is created but cannot allocate.** Quota is checked at allocation
  time, not at creation time. A cluster whose size has no family quota is created
  happily and fails when a job asks for a node. This is why US2's quota scenario
  is checked against the live quota and why the verification job matters: a
  cluster that has never allocated a node is an untested cluster.
- **The verification job fails for a reason unrelated to data access.** A missing
  environment, a bad script path, or an image pull failure produces a red job
  that says nothing about the data store. The evidence must distinguish "the
  workspace may not read this" from "the job did not run", exactly as feature 003
  distinguished an authorisation refusal from any other failure.
- **The job succeeds without reading anything.** A job that starts, logs, and
  exits zero would satisfy a naive check. This is why the output must be derived
  from the file's contents.
- **Nodes are still up when the check runs.** Reading the node count immediately
  after a job finishes will show nodes that have not yet scaled down, and
  recording that as a failure would be as wrong as recording an early zero as a
  success. The check is made after the declared idle interval has elapsed.
- **The deployment role needs more than one operation.** Two new resource types
  are involved, and reads are not recorded in the same way writes are. Several
  failures in a row are expected; each is a separate amendment with its own
  provenance, not an excuse to add a group of operations at once.
- **A failing deployment command never reached the platform.** The tooling
  resolves the subscription from a local cache first, and a client-side failure
  can read like a refusal. It is not one, and must not be recorded as one.
- **The deployment partially succeeded.** A red run is not proof that nothing was
  deployed; a green run is not proof that something was. The deployment history
  is the record, not the workflow's colour.
- **A cost reading of null.** On this subscription the usage API has returned
  records with no cost populated. A null is not a zero, and a single window is
  not a comparison.
- **The job is left running.** The one way this feature can cost real money. The
  cluster's automatic scale-down bounds it, but the session does not close until
  the node count has been observed back at zero.

## Requirements *(mandatory)*

### Functional Requirements

**Declaration**

- **FR-001**: Both objects MUST be declared in the infrastructure template that
  continuous integration deploys. Neither may be created by hand from a console
  or a command line: an object that exists but is not declared is one the next
  deployment does not know about.
- **FR-002**: The data store MUST point at storage the project already deploys.
  No new storage account is created, because none is needed and each one is a new
  billing surface.
- **FR-003**: The data store MUST authenticate by identity. It MUST NOT carry an
  account key or a shared access signature, in the template or in the deployed
  object — consistent with the workspace's existing key-free configuration, and
  because a credential in a template is a credential in a repository.
- **FR-004**: The data store MUST be distinguishable from the stores the
  workspace creates for its own housekeeping. Training data and workspace system
  artifacts do not share a location.

**Cost shape**

- **FR-005**: The cluster MUST be declared with a minimum node count of zero, so
  that it holds no allocated nodes when no job is running.
- **FR-006**: The cluster's maximum node count MUST be two, bounding the
  worst-case burn of a job left running while leaving batch scoring across nodes
  demonstrable.
- **FR-007**: The interval a node stays idle before it is released MUST be
  declared explicitly rather than left to the service default. The default is
  roughly two minutes of billed time appended to every job; the point is not the
  amount but that the value is chosen and known.
- **FR-008**: The feature MUST NOT create a compute instance, a real-time
  endpoint, or a real-time deployment. Each is billed while doing nothing, and
  each is out of scope for week 2.

**Size selection**

- **FR-009**: The node size MUST be allocatable on this subscription: its family
  MUST have a non-zero dedicated quota, and the cluster's maximum vCPU demand
  MUST fit within both the per-family limit and the regional dedicated total.
  Being offered by the service's list of supported sizes does not satisfy this —
  the cheapest supported size in this region has a family quota of zero.
- **FR-010**: The cluster MUST request dedicated nodes. Low-priority nodes MUST
  NOT be used: the regional low-priority quota on this subscription is zero, so
  the request could never be satisfied, and the per-family readings that suggest
  otherwise are gated by that regional total.
- **FR-011**: Among the sizes that satisfy FR-009 and FR-010, the size chosen
  MUST be the cheapest per node-hour that is supported for both training jobs and
  batch scoring.

**Deployment authority**

- **FR-012**: The deployment MUST be performed by continuous integration, through
  the existing approval gate, and the gate MUST be passed by a human decision.
- **FR-013**: When the deployment fails for want of an operation the deployment
  role does not hold, **exactly the operation named in the error** MUST be added
  to that role, and no other. Operations MUST NOT be added in anticipation.
- **FR-014**: Every operation added MUST record the identifier of the run whose
  failure demanded it, in the same place feature 003 records provenance. An
  operation with no failing run behind it MUST be removed rather than justified.
- **FR-015**: A predefined role MUST NOT be assigned to resolve any failure in
  FR-013. Doing so would end the interruption and simultaneously end the property
  the narrow role exists for, which feature 003's boundary checks would then
  detect as a defect.

**Observations**

- **FR-016**: Two questions this project recorded as open MUST be answered by
  observation and written down with the date they were observed, each with both
  outcomes acceptable:

  **Resource-group authority** — whether the authority the workspace was
  deliberately denied is actually required when the first compute target is
  created.

  **Load balancer at rest** — whether a cluster holding zero nodes incurs a
  charge that is not node-hours.

  Neither is a requirement to satisfy. Recording an expectation as a result does
  not discharge this requirement.

**Evidence and cost**

- **FR-017**: The claim that the cluster rests at zero nodes MUST be settled by
  reading the deployed resource's reported node counts from the service. The
  template's declaration MUST NOT be accepted as evidence for it.
- **FR-018**: The claim that the workspace can read through the data store MUST
  be settled by a job whose output is derived from the contents of a file read
  through that store. Neither the existence of the data store record nor a
  read performed with the author's own credentials satisfies this.
- **FR-019**: Evidence MUST distinguish an authorisation refusal from any other
  failure, and MUST distinguish a failure that reached the platform from one that
  did not.
- **FR-020**: Cost MUST be re-checked before the feature closes, by comparing two
  time windows rather than reading one. A record with an unpopulated cost MUST
  NOT be read as a cost of zero.
- **FR-021**: The feature MUST NOT close while any node is allocated. The final
  observed state of the cluster is zero nodes.

### Key Entities

- **Data store** — a named reference the workspace holds to a location in
  storage, carrying how to authenticate to it. It is metadata: it holds no data
  and costs nothing itself.
- **Compute cluster** — a managed pool that allocates nodes when work arrives and
  releases them when work ends. Its cost is entirely a function of node-hours
  consumed; the pool itself is free.
- **Node count at rest** — what the service reports the cluster is currently
  holding. The distinction between what was requested and what is true.
- **Verification job** — a minimal unit of work whose only purpose is to prove
  the two objects work together, by reading a known file through the data store
  on a node of the cluster.
- **Provenance entry** — a record binding one operation added to the deployment
  role to the identifier of the run that failed for want of it.

## Success Criteria *(mandatory)*

Each criterion names the axis on which it fails, because a check that dies on
the wrong axis is green for the wrong reason. None is settled by reading the
template that requested the outcome.

### Measurable Outcomes

- **SC-001**: A gated deployment run completes and the environment's deployment
  history contains a record created during that run whose state is succeeded.
  *Fails on*: the deployment being refused or rejected. A green workflow that
  deployed nothing does not satisfy this.
- **SC-002**: After deployment and before any job is submitted, the cluster read
  back **from the service** reports zero nodes in every category it counts.
  *Fails on*: the cluster holding allocated nodes at rest. A template declaring a
  minimum of zero does not satisfy this — that is the request, not the result.
- **SC-003**: A job submitted to the cluster completes successfully, and its
  output is a value derived from the contents of a file it read through the data
  store — a checksum, a byte count, or a row count that cannot be produced
  without having read the bytes. *Fails on*: the workspace being unable to reach
  the data. A job that runs and produces a constant satisfies nothing.
- **SC-004**: During that job, the cluster is observed holding at least one
  allocated node, and after the declared idle interval has elapsed it is observed
  back at zero without manual intervention. *Fails on*: scale-down not happening.
  Both halves are required: the first proves the cluster can allocate, the second
  proves it stops.
- **SC-005**: The vCPU demand the cluster can reach is within the per-family
  dedicated quota and within the regional dedicated total, both read from the
  live subscription, and the cluster requests dedicated rather than low-priority
  nodes. *Fails on*: a size that cannot be allocated here. SC-003 is the
  independent confirmation: a node that started is a quota bound that held.
- **SC-006**: Every operation added to the deployment role during this feature
  maps to the identifier of a run that failed for want of it, and the count of
  added operations equals the count of provenance entries. Zero operations
  survive unaccounted for, and no predefined role was assigned. *Fails on*:
  authority granted in anticipation rather than in response.
- **SC-007**: Feature 003's boundary checks still refuse what they refused
  before, after the role has been amended. *Fails on*: an amendment having
  widened the role beyond the operation named.
- **SC-008**: Cost attributable to this feature, read from the cost report by
  comparing two time windows, is under 1 € and consists only of node-hours for
  the period the verification job ran. *Fails on*: an unexpected meter. A single
  reading, or a record with an unpopulated cost, does not satisfy this.
- **SC-009**: Both observations in FR-016 are written down, each stating what was
  observed and on what date. *Fails on*: an expectation recorded as a result. A
  finding of "the denied authority was not needed" and a finding of "it was
  needed, and here is the error" both satisfy this equally.
- **SC-010**: At the moment the feature is closed, the cluster holds zero nodes
  and no compute instance and no real-time deployment exists in the workspace.
  *Fails on*: something left running.

## Assumptions

- The resource group, the workspace, the storage account, and the gated
  deployment path all exist from features 001 to 003 and are unchanged by this
  feature except where a deployment failure proves a change is required.
- The data store points at a dedicated location inside the storage account
  already deployed. Reusing the container the workspace created for its own
  artifacts would work and was rejected: training data and system artifacts
  sharing a location is a habit that costs nothing to avoid now and is awkward to
  unpick later.
- The workspace's identity already holds data access on that storage account,
  granted and maintained by the platform, as recorded in feature 002. If that
  proves insufficient for a location the platform did not create, the resulting
  failure is a finding for FR-016 rather than a defect.
- The verification job's workload is deliberately trivial. It exists to prove the
  path, not to train anything; the training script is the next feature's subject.
- The figures this specification relies on — quotas, rates, and which sizes are
  allocatable — were measured against this subscription on 2026-08-11 and are
  taken as given. Re-measuring them is not part of this feature. If an
  observation contradicts one of them, the contradiction is the finding.
- The budget alert is reconfirmed in the portal before the first hourly resource
  is created. The command-line tooling cannot settle whether it exists, and with
  the spending limit off it is the only notification that exists.
- One author approves their own gated deployment. That gate is a deliberate
  pause, not a separation of duties, and this specification does not claim the
  stronger property.

## Out of Scope

- Any training script, model, experiment tracking, or model registration. This
  feature builds what those will run on; it does not run them.
- Compute instances, in any configuration. Billed while stopped, and deletable
  rather than stoppable is the only correct handling — so none is created.
- Automated machine learning and hyperparameter sweeps. Both multiply cluster
  hours for a capability the exam asks the candidate to choose rather than to
  operate.
- Real-time endpoints and their deployments, and everything that presupposes them
  — progressive rollout, blue/green, rollback.
- Batch endpoints themselves. The cluster is specified so that one can run on it
  later; creating one is a later feature.
- Network isolation for the workspace, which remains closed in theory as a
  declared cost decision from week 1.
- Changing the workspace's identity type, which is deferred to the teardown when
  it costs one line rather than a session.
