# Feature Specification: Deployment from continuous integration, without a stored secret

**Feature Branch**: `003-ci-oidc-deploy`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Deploy the infrastructure from GitHub Actions,
authenticated to Azure with OIDC federated credentials and no secret stored in
the repository. The deployment principal is created by the author, granted its
role by the author, at a scope the author chooses — least privilege is genuinely
reachable here, and the feature must actually reach it."

## Context

This feature is written as the deliberate counterpart to feature 002, and the
contrast is the reason it is worth building.

Feature 002 tried to reduce the permissions of the workspace's platform-created
identity and could not. The platform maintains that identity's grants: a deleted
grant was recreated, under a new name, within seconds, inside the same
deployment. Least privilege was unreachable there because the permissions were
never the author's to set. See
[002 research, R10](../002-workspace-identity-least-privilege/research.md).

Here every element of the identity is the author's: the principal is registered
by the author, the trust that lets continuous integration assume it is written
by the author, and the authority it holds is granted by the author at a scope
the author chooses. Nothing about it is maintained by the platform. **Least
privilege is therefore reachable, and this feature is only successful if it is
actually reached** — not declared, not approximated.

### What feature 002 taught about writing success criteria

002's SC-003 read: *"enumerating the permissions held by the workspace identity
returns zero grants scoped to the resource group or above."* After the change it
**passed**, verified by command — while the reduction it existed to guarantee had
not happened. One resource-group-wide grant had been replaced by three
resource-scoped grants of equivalent authority. The criterion measured the
wording of a scope, so a change that relocated authority without reducing it
satisfied it.

Every criterion below is therefore written to be **unsatisfiable by a change
that defeats its purpose**. Where a criterion could be met by inspecting a
configuration, it is instead met by attempting an action and recording what
happened. A permission boundary that has never been pushed against is an
assumption, not a boundary.

### What "least privilege" means here, operationally

Two properties, both testable, and neither sufficient alone:

- **Bounded** — an action attempted outside the declared scope is refused, and
  the refusal is recorded.
- **Necessary** — each authority granted is load-bearing: withdraw it and the
  deployment fails. An authority that can be withdrawn with no observable
  consequence is not least privilege, it is decoration.

002 produced exactly such a decoration: a permission grant the template owns
which changes nothing, because a broader platform grant subsumes it. This
feature must not repeat it.

## Clarifications

### Session 2026-08-09

- Q: What does the trust condition bind to — the repository's default branch, or
  a named approval gate a run must pass before it can authenticate? → A: **the
  approval gate**. It narrows the trusted context further than a branch does,
  and it puts a human decision in front of every deployment. It also yields a
  sharper negative test than a branch would: a run on the correct branch, of the
  correct repository, that has simply not been approved is refused *at
  authentication*. That refusal cannot be explained away as a misconfiguration —
  it is the boundary working.
- Q: How narrow is the identity's authority within its scope — general resource
  management through predefined roles, or authority restricted to exactly the
  resource types this template declares? → A: **restricted to exactly what the
  template declares**. A predefined general-management role would leave the
  identity able to create any resource in the container, including billable ones,
  which is a boundary the cost principle should not depend on nobody crossing.
  The narrow option also means the minimum cannot be assumed: it is discovered by
  deploying, failing, and reading which operation was refused. That discovery is
  the substance of the feature.
- Q: What is the unit of "authority" that FR-008 and SC-007 withdraw and re-test
  — the whole grant, each resource type's operations, or each single operation?
  → A: **the discovery record proves the operations; the explicit withdrawal test
  applies once, to the grant as a whole**. Discovery already produces the
  necessity evidence for free: an operation is in the role *because* a named
  deployment failure demanded it, and that failure is the proof. Re-withdrawing
  it to reproduce the same failure demonstrates nothing new at a cost of one
  deployment cycle each. The rigour is kept by making the record binding in the
  destructive direction — an operation with no failure behind it is deleted, not
  argued for.
- Q: What starts the deploying workflow? → A: **both an accepted change to the
  infrastructure on the default branch, and a manual request by the author** —
  each still subject to the approval gate. The manual path is not a convenience:
  SC-004 and SC-007 need runs that are not merges, and without it they would be
  triggered by empty commits, which is noise in the history for nothing. Neither
  path is reachable without write access to the repository, so FR-014 holds.
- Q: Does an empty result count as a refusal? → A: **no. Only an explicit
  authorization denial counts.** The platform filters enumerations by permission,
  so a listing run without authority returns success with zero items —
  indistinguishable from "there is nothing there". That is the same vacuity that
  let 002's SC-003 pass. Probes therefore target **named** resources rather than
  listings, which also means a second, empty resource container must exist purely
  as a probe target. It is created by the author, costs nothing, and removes the
  remaining ambiguity between "you may not" and "it is not there".
- Q: How is the operation set discovered in practice? → A: **in two observational
  passes.** First, derive it from the record of what the deployment actually did
  — the environment keeps an account of every operation it invoked, and reading
  that is observation, not assumption. Second, verify by deploying as the
  identity; whatever the first pass missed surfaces as a failure and is added one
  operation at a time. The second pass is needed because the record does not
  capture every read the platform performs on the way. Read alone would be
  incomplete; trial alone would cost twelve to eighteen gated runs before the
  first success. Neither pass consults documentation for what *ought* to be
  needed, which is what FR-006a forbids.

## Cost

**Expected added cost: zero.** Every component this feature introduces is
control-plane metadata or free tooling: an application registration, its trust
conditions, permission grants, and automation minutes on a public repository.
The deployment it performs is a redeploy of the template already in place and
must leave the environment resource-for-resource identical.

The refusal evidence costs nothing by construction: a refused action fails at
authorization, before any resource is touched. If any part of this feature would
introduce a billable resource, that part is out of scope and is surfaced rather
than implemented.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Continuous integration deploys, holding no secret (Priority: P1)

The author pushes an infrastructure change. Continuous integration authenticates
to the cloud provider, deploys the template to the existing environment, and
reports success — without any credential existing in the repository, in its
settings, or anywhere else that could be copied and replayed.

**Why this priority**: It is the objective. Without it there is nothing to bound.

**Independent Test**: Trigger the deploying workflow and confirm it completes
green, and that the environment's deployment history contains a new record,
succeeded, timestamped inside that run. A preview or a validation does not count.

**Acceptance Scenarios**:

1. **Given** no credential is stored anywhere for this identity, **When** the
   deploying workflow runs from the trusted context, **Then** it authenticates
   successfully and the deployment completes.
2. **Given** the deployment has completed, **When** the environment's deployment
   history is read, **Then** it contains a record created during that run whose
   state is succeeded.
3. **Given** the deployment has completed, **When** the environment's resources
   are enumerated, **Then** the inventory is identical to the one captured
   before the run — nothing added, nothing removed, no tier changed.
4. **Given** the workflow succeeded once, **When** it is run again unchanged,
   **Then** it succeeds again and the inventory is still unchanged.

---

### User Story 2 - The identity's reach is proven bounded (Priority: P1)

The author attempts, as the deployment identity, actions that fall outside the
scope it was granted. Each attempt is refused. The command and the refusal are
recorded as evidence.

**Why this priority**: It is the exit criterion. The feature's claim is about
what the identity *cannot* do, and that claim is worthless unproven.

**Independent Test**: Testable as soon as the identity and its grant exist,
before the workflow is written. Acquire a token as the identity, attempt the
out-of-scope actions, capture the errors.

**Acceptance Scenarios**:

1. **Given** a token held as the deployment identity, **When** a write is
   attempted at subscription scope, **Then** it is refused with an authorization
   error and nothing is created.
2. **Given** the same token, **When** a **named** resource container other than
   the declared one is read, **Then** the read is refused with an authorization
   error, recorded verbatim. An enumeration returning zero items does not
   satisfy this scenario.
3. **Given** the same token, **When** the identity attempts to grant itself or
   anything else authority outside the declared scope, **Then** the attempt is
   refused.
4. **Given** the recorded refusals, **When** the evidence is reviewed, **Then**
   each entry contains the exact command issued and the error returned — not a
   description of why the configuration makes it impossible.

---

### User Story 3 - Only the trusted context can become the identity (Priority: P2)

Knowing the identity's public identifiers is not enough to act as it. A run from
an untrusted context, and a login attempt made from outside continuous
integration using only what the repository stores, are both refused at
authentication.

**Why this priority**: Bounding *what* the identity may do is half the boundary.
The other half is bounding *who* may become it. Story 2 without this leaves the
identity assumable by anyone who reads the repository.

**Independent Test**: Let a run reach authentication without approval and
capture the refusal. Attempt authentication from a context that does not satisfy
the trust condition at all and capture that refusal. Attempt to authenticate as
the identity from the author's own machine using only values the repository
stores, and capture the third.

**Acceptance Scenarios**:

1. **Given** a run of this repository, on the branch that deploys, **When** it
   reaches authentication without having passed the approval gate, **Then** it is
   refused at authentication and the error is recorded.
2. **Given** the identity's trust condition, **When** authentication is
   attempted from a context that does not satisfy it at all, **Then** it fails at
   the authentication step, before any authorization decision, and the error is
   recorded.
3. **Given** only the identifiers stored in the repository, **When**
   authentication as the identity is attempted from the author's machine,
   **Then** it is refused.

---

### User Story 4 - Pull requests still validate, and cannot deploy (Priority: P2)

A contributor with no access to the environment opens a pull request touching
the infrastructure. The template is validated, as it is today. The deploying
workflow does not run, and could not have authenticated if it had.

**Why this priority**: The validation path is existing, working behaviour that
this feature must not break. Contributions from a fork are the case that makes
it matter.

**Independent Test**: Open a pull request that modifies the infrastructure and
observe which workflows run for it.

**Acceptance Scenarios**:

1. **Given** a pull request that modifies the infrastructure, **When** its
   checks run, **Then** the validation workflow runs and completes green.
2. **Given** the same pull request, **When** the repository's run history for it
   is read, **Then** the deploying workflow has no run for that event.
3. **Given** the validation run, **When** its own log of granted token
   permissions is read, **Then** it holds no permission to request an identity
   token and reads no stored value.

---

### User Story 5 - No granted authority is inert (Priority: P3)

The grant the identity holds is withdrawn and the deployment is re-run: it must
break, and restoring the grant must fix it. Inside the role, every permitted
operation is traced back to the deployment failure that demanded it, and any
operation that cannot be traced is deleted.

**Why this priority**: It is what separates this feature from 002's outcome,
where a declared grant turned out to do nothing at all. It is last because it
can only run once the deployment is known to work.

**Independent Test**: Remove the grant, run the deployment, record the failure,
restore the grant, run the deployment, record the success. Separately, walk the
final role against the discovery record and account for every operation from
either pass.

**Acceptance Scenarios**:

1. **Given** a working deployment, **When** the identity's grant is withdrawn,
   **Then** the next run fails with an authorization error.
2. **Given** that failure, **When** the grant is restored, **Then** the next run
   succeeds again.
3. **Given** the final role, **When** each permitted operation is looked up in
   the discovery record, **Then** every one of them is accounted for by a line in
   the derivation pass or by a verification failure that named it.
4. **Given** an operation the discovery record does not account for, **When** the
   feature closes, **Then** that operation is not present in the final role.

---

### Edge Cases

- **The template declares a permission grant of its own.** Creating a permission
  grant is not part of ordinary resource management authority. If the deployment
  identity is given only enough authority to manage resources, the deployment
  fails at that step. This is expected to surface as a real failure during the
  work, and is the point at which the true minimum becomes visible rather than
  assumed. It must not be resolved by widening authority beyond the declared
  scope.
- **The environment's container is a precondition, not a deliverable.** The
  identity is scoped *to* it and therefore cannot create it. If it does not
  exist, the deployment fails, and that failure is correct.
- **Two runs overlap.** A second run starting while a deployment is in flight
  must not corrupt the environment or leave a partially applied state.
- **The identity is assumed from a context that satisfies the trust condition
  but was not intended** — for instance a run triggered by a mechanism nobody
  considered. The trust condition must be narrow enough that this is not
  reachable from a fork.
- **The deployment history fills with failures.** Discovery works by failing, so
  the environment's history will hold several failed records before a succeeded
  one. They are evidence, not mess. SC-001 must be read as requiring *a*
  succeeded record from the final run, not a clean history.
- **A failure during discovery is mistaken for a boundary.** Overlapping runs,
  or a deployment that failed for an unrelated reason, can produce errors that
  read like authorization refusals. FR-017 applies to discovery too: an operation
  is added to the role only when the failure actually names it.
- **The narrow authority goes stale.** When the template gains a resource type,
  the identity will not be permitted to create it and the deployment will fail.
  That is the correct behaviour, not a defect: it is the cost of FR-006 and it
  must be written down where the next person deploying will find it, so the
  failure is recognised rather than debugged.
- **The approval gate is passed by the same person who wrote the change.** With
  a single author this is unavoidable and the gate is a deliberate pause rather
  than a separation of duties. The specification must not claim the stronger
  property.
- **The withdrawal test leaves the environment without a working deployment
  path.** Every withdrawal must be paired with a restore, and the final state
  must be the working one.
- **A refusal that is not an authorization refusal.** An action that fails
  because a name is wrong, a resource is missing, or a request is malformed
  proves nothing about the boundary. Evidence must distinguish "you may not"
  from "that did not work".

## Requirements *(mandatory)*

### Functional Requirements

**Identity and trust**

- **FR-001**: Continuous integration MUST authenticate to the cloud provider
  without any credential stored in the repository, in its settings, or in its
  history. Values stored to identify the target MUST be identifiers that confer
  no access on their own.
- **FR-002**: The identity used MUST have no password and no certificate
  credential in existence, at any point, including during setup.
- **FR-003**: Trust MUST be conditional on the identity of the run, not merely
  on the repository. A run that does not satisfy the condition MUST be refused at
  the authentication step, before any authorization decision is reached.
- **FR-004**: The trust condition MUST bind to a **named approval gate**: only a
  run that has passed it may authenticate. A run of the same repository, on the
  same branch, that has not passed the gate MUST be refused — and refused at
  authentication, not merely blocked from starting.
- **FR-004a**: Passing the gate MUST require a human decision. An automatic pass
  would satisfy FR-004's wording while removing the checkpoint it exists for.

**Authority**

- **FR-005**: The identity's authority MUST be confined to the single resource
  container holding the deployed environment. It MUST hold no authority at
  subscription scope, and none over any other container.
- **FR-006**: Within that scope, the identity's authority MUST be restricted to
  the operations the deployed template actually requires, on the resource types
  it actually declares. A predefined role granting general management of the
  container does NOT satisfy this: it would leave the identity able to create
  resource types the template never mentions, including billable ones.
- **FR-006a**: The set of operations MUST be **discovered**, not assumed, in two
  observational passes:

  **Derivation** — from the environment's own record of the operations a
  deployment invoked. This is reading what happened, not predicting what might be
  needed.

  **Verification** — by deploying as the identity. Anything the first pass missed
  surfaces as a failure naming the operation, and only that operation is added.

  Consulting documentation for what a deployment of this kind *ought* to require
  is not discovery and MUST NOT be the basis for any operation in the role.
- **FR-006c**: Every operation in the final role MUST trace to one of the two
  passes — a line in the derivation record, or a recorded verification failure.
  An operation traceable to neither MUST be removed.
- **FR-006b**: The identity MUST NOT be able to create a resource type the
  template does not declare. Demonstrated by attempting one and recording the
  refusal, not by reading the list of permitted operations.
- **FR-007**: The identity MUST hold enough authority to perform every operation
  the template requires, including creating the permission grant the template
  declares, and no authority beyond that set.
- **FR-008**: Every authority the identity holds MUST be necessary, established
  at two levels:

  **Each operation** — an operation is permitted only if FR-006a's discovery
  record accounts for it: a line in the derivation record, or a verification
  failure that named it. That record is the evidence, and it is binding in the
  destructive direction — an operation it does not account for MUST be removed
  from the role, not justified in prose. No separate withdrawal cycle is run per
  operation, because discovery already demonstrated the necessity of each one.

  **The grant as a whole** — withdrawing the identity's grant MUST cause the
  deployment to fail, and restoring it MUST make the deployment succeed again.
  This is run explicitly, and it is the check 002 would have failed: it proves
  the grant is what authorizes the deployment, and not something else.
- **FR-009**: The identity MUST NOT be able to create or delete the resource
  container it is scoped to.

**Deployment**

- **FR-010**: The deployment performed by continuous integration MUST be a real
  deployment recorded in the environment's deployment history — not a preview,
  a dry run, or a validation.
- **FR-011**: The deployment MUST leave the environment's resource inventory
  unchanged: no resource added, none removed, none moved to a different service
  tier.
- **FR-012**: Repeating the deployment with an unchanged template MUST succeed
  and MUST leave the inventory unchanged.

**Separation from validation**

- **FR-013**: The existing validation behaviour MUST continue to run for pull
  requests, including pull requests originating from a fork, holding no
  credential and requesting no identity token.
- **FR-014**: The deploying behaviour MUST NOT be reachable by any event that a
  contributor without write access to the repository can cause.
- **FR-014a**: The deploying behaviour MUST be startable in two ways: by an
  accepted change to the infrastructure on the default branch, and by an explicit
  request from someone with write access. Both MUST pass the approval gate; a
  path that bypasses it would defeat FR-004.
- **FR-015**: Validation and deployment MUST remain separable, so that a change
  to one cannot silently grant the other access it did not have.

**Evidence**

- **FR-016**: The boundary of the identity's authority MUST be demonstrated by
  attempted actions that were refused, each recorded with the exact command
  issued and the error returned. An argument that the configuration makes the
  action impossible does not satisfy this requirement.
- **FR-017**: Evidence MUST distinguish an authorization refusal from any other
  failure. A failure caused by a bad name, an absent resource, or a malformed
  request is not evidence of a boundary.
- **FR-017a**: Only an explicit authorization denial counts as a refusal. A
  successful call returning an empty result MUST NOT be recorded as evidence: the
  platform filters enumerations by permission, so an empty listing is
  indistinguishable from an empty scope.
- **FR-017b**: Probes MUST therefore target **named** resources, not listings.
  Where the boundary being tested is access to another resource container, a
  second, empty container MUST exist to be named — so that a refusal cannot be
  confused with the absence of a target.
- **FR-018**: A reversal MUST be recorded as runnable commands: how to revoke
  the identity's access, remove the trust, and return the repository to its
  previous state.

**Cost**

- **FR-019**: The feature MUST NOT create any billable resource. If reaching a
  requirement would require one, the requirement is reported as unmet rather
  than met at a cost.

### Key Entities

- **Deployment identity** — the principal continuous integration acts as.
  Registered by the author, holding no stored credential, distinct from the
  workspace's own platform-managed identity.
- **Trust condition** — the rule stating which runs may become the deployment
  identity. Evaluated at authentication time; failing it produces an
  authentication error, not an authorization error.
- **Authority grant** — a permission held by the deployment identity, at a named
  scope. Subject to the necessity test in FR-008.
- **Deployment record** — the environment's own account of a deployment having
  happened, with a state and a timestamp. The distinction between "the workflow
  was green" and "something was deployed".
- **Refusal evidence** — a captured command and its error, proving a boundary was
  pushed against and held.

## Success Criteria *(mandatory)*

Every criterion below is settled by an observation. None is settled by reading a
configuration and forming a judgement, and none can be satisfied by a change that
relocates authority rather than reducing it — the failure mode of 002's SC-003.

### Measurable Outcomes

- **SC-001**: A workflow run triggered from the trusted context completes green,
  **and** the environment's deployment history contains a record created during
  that run whose state is succeeded. Green alone does not satisfy this: a
  workflow that validated and reported success would pass it. The history will
  also contain failed records from discovery; they do not count against this
  criterion, which asks for one succeeded record from the final run.
- **SC-002**: The environment's resource inventory taken after the run is
  identical to the inventory taken before it — same resources, same names, same
  count, same service tiers.
- **SC-003**: At least four actions attempted **as the deployment identity** are
  refused with authorization errors, each recorded with the exact command and the
  exact error. They MUST cover both axes of the boundary:

  *Outside the scope* — one **write at subscription scope**; one **access to a
  resource container other than the declared one**; one **attempt by the identity
  to grant authority outside its scope**.

  *Inside the scope, outside the authority* — one attempt to **create a resource
  type the template does not declare**, in the container the identity is scoped
  to. This is the axis a predefined general-management role would have left open,
  and it is the one that proves the narrow authority is real.

  Each of the four MUST be an explicit authorization denial against a **named**
  target. A call that succeeds and returns nothing is not a refusal and does not
  count. A criterion satisfied by enumerating grants and observing their scope
  wording does not satisfy this one either — that is precisely the check that
  passed in 002 while the objective was missed.
- **SC-004**: Three authentication refusals are recorded, each with its error:

  1. A run of **this repository, on the branch that deploys, that has not passed
     the approval gate** — refused at authentication. This is the sharpest of the
     three: everything about it is legitimate except the gate.
  2. An authentication attempt from a context that does not satisfy the trust
     condition at all.
  3. An authentication attempt made from the author's own machine using only the
     values the repository stores.

  Each must fail at authentication, before any authorization decision — an
  authorization error would mean the context was trusted after all.
- **SC-005**: A pull request modifying the infrastructure produces a run of the
  validation workflow that completes green, and **no run of the deploying
  workflow appears in the repository's run history for that event**.
- **SC-006**: At the moment the successful deployment completed, the identity had
  zero password credentials and zero certificate credentials in existence.
  Verified by enumeration after the fact, and made meaningful by SC-001 having
  already succeeded — the deployment demonstrably happened while no secret
  existed.
- **SC-007**: Necessity is settled at both levels of FR-008:

  **Operations** — every operation in the final role maps to an entry in the
  discovery record: either a line in the derivation pass, or a verification
  failure that named it. The count of operations equals the count of record
  entries accounting for them. Zero operations survive unaccounted for.

  **The grant** — withdrawing it and re-running the deployment produces a
  failure; restoring it and re-running produces a success. Both runs are
  recorded. A withdrawal that leaves the deployment working means something
  other than this grant is authorizing it, and the feature is not done.
- **SC-008**: The environment's cost report for the days spanning this feature
  shows no meter that was not already present, and the total attributable to this
  feature is **0.00**.
- **SC-009**: Every step of the recorded reversal is a runnable command, and the
  count of things created by this feature matches the count of removal commands
  written down.

## Assumptions

- The resource container and the environment inside it already exist, deployed
  by feature 001 and unchanged by feature 002's attempt. This feature deploys
  into them and does not create them.
- The repository is public, so automation minutes are free, and pull requests
  from a fork are a realistic case rather than a hypothetical one.
- Identifiers that name the target of authentication — which directory, which
  application, which subscription — are not credentials. They appear in run logs
  as a matter of course. SC-004 exists to prove that possessing them grants
  nothing.
- The out-of-scope actions used as evidence are chosen so that a *successful*
  one would create nothing billable. A resource container costs nothing to
  create and would be removed immediately if the refusal unexpectedly did not
  occur. The same applies to the probe for FR-006b: the resource type attempted
  inside the declared scope must be one that carries no charge even if the
  attempt unexpectedly succeeds.
- A second, empty resource container exists solely as a probe target for
  FR-017b. It is created by the author, holds nothing, carries no charge, and is
  removed by the reversal in FR-018.
- Fork behaviour is verified through what the repository observably runs for a
  pull request, and through the trust condition refusing an untrusted context
  (SC-004). Standing up a second account to author a genuine fork pull request is
  not required to settle SC-005.
- The template deployed is the one currently in place, unchanged by this feature
  except where a deployment failure proves a change is required.
- Both clarified choices are assumed free, and this is checked before either is
  built rather than after: a role defined for a specific purpose is control-plane
  metadata, and an approval gate on a public repository is part of the free tier.
  If either turns out to carry a charge, FR-019 applies and the choice is
  revisited rather than paid for.
- The approval gate is a checkpoint, not a separation of duties. There is one
  author, who will approve their own runs.

## Out of Scope

- The workspace's own identity: its type, and the grants the platform maintains
  on it. Feature 002 closed on that question and deferred the remaining one to
  the teardown.
- Tearing down or recreating the environment.
- Any deployment target other than the existing environment — no second
  environment, no staging copy, nothing that would multiply resources.
- Deploying anything the template does not already declare.
