# Feature Specification: Least-privilege permissions for the workspace identity

**Feature Branch**: `002-workspace-identity-least-privilege`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Constrain the machine learning workspace's managed
identity to the least privilege it actually needs on the resources already
deployed, and make those permissions declared in the infrastructure template
rather than granted invisibly by the platform."

## Context

This feature does not start from an empty slate, and that shapes everything
below.

The environment described by feature 001 is deployed and live. When the
workspace was created, the platform granted its managed identity **four**
permission grants that appear nowhere in the template. This was observed
against the live subscription before this specification was written, not
assumed:

| What the grant covers | Its scope | Created by |
| --- | --- | --- |
| Wildcard control over the secret store, the storage account, container registries, and the ability to write resource groups | the **whole resource group** | a platform service principal, at workspace creation |
| Read and write of stored data objects | the storage account only | same |
| Privileged read and write of stored file shares | the storage account only | same |
| Full management of the secret store, including its access configuration | the secret store only | same |

Three consequences follow, and each one constrains the requirements:

1. **There is nothing minimal left to add.** The identity is already
   over-provisioned relative to what this project does. A purely additive
   feature would be empty.
2. **The template cannot simply re-declare what exists.** The platform rejects
   an identical permission — same identity, same capability, same scope —
   requested under a different grant name, and the existing grant names were
   generated randomly by the platform and cannot be reproduced. Declaring them
   as they stand would pass a dry run and then fail the real deployment.
3. **Recreating the environment would not help.** The platform performs these
   grants whenever a workspace is created, so a clean rebuild reproduces the
   same situation.

The feature is therefore a **reduction**, not an addition: bring the identity
down to permissions this project can name a need for, and put the survivors
under the template's ownership.

## Clarifications

### Session 2026-08-07

- Q: Which grants does the template take ownership of? → A: All of the ones that
  survive. Each surviving permission is removed in the form the platform created
  it and recreated by the template under a deterministic name, so that reading
  the template answers the question in full rather than for one grant out of
  four.
- Q: How narrow should the surviving permissions be? → A: Narrow to what the
  environment needs today. A permission whose only justification is a capability
  this project has not built yet is dropped, accepting that a later exercise will
  hit an authorization error and re-grant it deliberately.
- Q: What counts as proof that the identity still works? → A: An operation the
  service performs under its own identity, paired with a negative control that
  shows the same operation failing when the permission is withheld. A command
  authenticated as the author proves nothing, because the author's own authority
  would carry it either way.
- Q: The dry run revealed that the system data stores authenticate with account
  keys, not with the identity — invalidating the reason written for keeping the
  storage permission. How to proceed? → A: Switch them to identity-based
  authentication and declare it in the template. Keys stop being used, the
  permission becomes genuinely load-bearing, and the reduction stops depending
  on a false premise. This modifies a deployed resource, so FR-009 is amended
  with a named exception rather than silently stretched.
- Q: Should the platform be stopped from re-granting resource-group authority?
  → A: Yes — declare the setting that controls it, rather than deleting the
  grant by hand and hoping it stays deleted. It also settles the question the
  Edge Cases had left to observation.
- Q: What happens if verification shows the workspace lost something it needed?
  → A: Restore the missing permission immediately using the recorded reversal,
  record which operation failed and which permission covered it, and stop for
  the author to decide. The environment is never left broken, and the failure
  becomes an input to the plan rather than a defect to diagnose later.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Take away the permission that exceeds any nameable need (Priority: P1)

The author wants the workspace identity to stop holding blanket authority over
the whole resource group. Today that single grant lets the identity do anything
to the secret store and the storage account, create and manage container
registries, and write resource groups — none of which corresponds to anything
this project has built or asked for.

**Why this priority**: it is the entire security value of the feature. Every
other story refines or protects this one. Without it, the identity keeps a
permission that would let a compromise of the workspace reach every resource
around it.

**Independent Test**: enumerate the permissions the identity holds and confirm
that none of them is scoped above an individual resource. Delivers value on its
own: the blast radius of the identity shrinks from the resource group to the
specific resources it uses, whether or not anything else in this feature lands.

**Acceptance Scenarios**:

1. **Given** the live environment, **When** the permissions held by the
   workspace identity are enumerated, **Then** no grant is scoped to the
   resource group or anything above it.
2. **Given** the reduction has been applied, **When** the remaining permissions
   are examined, **Then** none of them confers the ability to create or delete
   resources, and none confers wildcard authority over a resource type.
3. **Given** the reduction has been applied, **When** the resources in the
   environment are listed, **Then** the same five resources are present and no
   resource has been added, removed, or reconfigured.

---

### User Story 2 - Make every surviving permission visible in the template (Priority: P1)

The author reviews the template to know what the environment grants. Today the
template is silent about permissions, so the only way to answer "what can this
identity do?" is to query the live subscription. Each permission the identity
keeps must be declared in the template, so that reviewing the source answers the
question and a rebuild reproduces the same authority.

**Why this priority**: it is what makes the reduction durable rather than a
one-off manual edit. A permission trimmed by hand today and re-granted silently
tomorrow leaves no trace; a permission declared in the template is reviewable in
a diff. Equal priority to US1 because a reduction that is not recorded in the
source of truth does not survive the next rebuild.

**Independent Test**: read the template and enumerate the permissions it
declares; enumerate the permissions the identity actually holds; the two sets
match exactly, with no permission in one and not the other.

**Acceptance Scenarios**:

1. **Given** the template, **When** it is inspected, **Then** every permission
   the workspace identity holds is declared there, each one attached to the
   single resource it concerns rather than to the resource group.
2. **Given** a permission that the platform originally created, **When** the
   template takes ownership of it, **Then** the grant is identified by a name
   the template derives deterministically, so that repeating the deployment
   changes nothing rather than conflicting.
3. **Given** the template is deployed a second time with no edits, **When** the
   dry run is inspected, **Then** it reports no change at all.
4. **Given** the template, **When** it is inspected for identifiers, **Then**
   it contains no literal subscription, tenant, resource group, or identity
   identifier — every one of them is derived from the deployment context.

---

### User Story 3 - Confirm the workspace still works after losing the permission (Priority: P2)

The broad grant exists because the platform expects to use it. The author needs
evidence that removing it does not break the workspace at this project's current
stage, rather than an argument that it should not.

**Why this priority**: the reduction is worthless if it quietly disables the
environment, and the failure mode would surface much later — during a future
exercise — where it would be hard to attribute. It ranks below US1 and US2
because it verifies them rather than delivering the change.

**Independent Test**: after the reduction, cause the service to act under its
own identity against a resource it still has permission for, and confirm it
completes without an authorization failure. The check only counts if the same
operation is also seen to fail when that permission is withheld — otherwise a
pass proves nothing.

**Acceptance Scenarios**:

1. **Given** the reduction has been applied, **When** the workspace is queried,
   **Then** it reports itself as successfully provisioned, exactly as before.
2. **Given** the reduction has been applied, **When** the service reaches the
   storage account under its own identity, **Then** it succeeds without an
   authorization error.
3. **Given** the reduction has been applied, **When** the service reaches the
   secret store under its own identity, **Then** it succeeds without an
   authorization error.
4. **Given** a verification step that passes, **When** the permission it depends
   on is withheld and the step is repeated, **Then** it fails with an
   authorization error — establishing that the passing result was caused by the
   permission and not by the author's own authority.

---

### User Story 4 - Be able to put the permission back (Priority: P2)

Removing authority from a live workspace can break capabilities this project has
not reached yet. The author wants the way back written down before the removal
happens, not reconstructed under pressure afterwards.

**Why this priority**: it converts an irreversible-feeling change into a
reversible one, which is what makes US1 acceptable to attempt at all. It is P2
rather than P1 only because it protects the change instead of being the change.

**Independent Test**: read the recorded reversal and confirm every step is a
command that can be run as written, with no step that says to look something up
or work it out.

**Acceptance Scenarios**:

1. **Given** the reduction has been applied, **When** the author consults the
   deployment runbook, **Then** it states which permission was removed, what it
   allowed, and the exact command that restores it.
2. **Given** the recorded reversal, **When** it is followed, **Then** the
   identity is returned to the authority it held before this feature, with no
   step depending on a value that was not written down.
3. **Given** a future exercise that needs authority this feature removed,
   **When** the author consults the runbook, **Then** it says which capabilities
   are expected to require it, so the failure is recognised rather than
   diagnosed from scratch.

---

### Edge Cases

- **The platform may re-grant what was removed.** These grants are performed
  when a workspace is created. Whether the platform also restores them when an
  existing workspace is redeployed is not known and MUST be observed rather than
  assumed — if it does, the reduction is not durable and the feature's approach
  has to change.
- **A gap while ownership transfers.** Taking a permission out of the platform's
  hands and putting it in the template's means the old grant is removed and a
  new one created. Between the two the identity lacks that permission. This now
  applies to every permission that survives, not just to the one being removed,
  so there are several such windows rather than one. Nothing is running against
  this environment, so they are expected to be harmless — but the ordering must
  be deliberate rather than incidental, and no window may be left open at the
  end of a working session.
- **Requesting a permission that already exists fails.** The platform rejects a
  duplicate grant of the same capability to the same identity at the same scope
  when it is requested under a different name. Any permission the template
  declares must therefore not already exist in the form the platform created it.
- **The dry run cannot see what the platform will do.** Feature 001 already
  learned this: a dry run renders what the template declares, not what the
  service adds on its own. It will not reveal a permission the platform intends
  to grant during deployment. This limits what the dry run can prove and is why
  a post-deployment check is required as well as a pre-deployment one.
- **The reduction is correct for this stage only.** Capabilities this project
  has not reached — provisioning compute, creating a container registry on
  demand, standing up an endpoint — are plausible consumers of the broad grant.
  The reduction is scoped to what exists today and must be revisited when those
  arrive, rather than treated as settled.
- **A permission the template does not declare is never removed by deploying
  it.** Deployment adds and updates; it does not delete what it was not told
  about. Removing the broad grant is therefore a separate, deliberate act, not a
  side effect of deploying the template.
- **Narrowing can go too far.** A permission that looks excessive may cover a
  path the workspace uses without announcing it. Each reduction needs a stated
  reason for believing the capability is unused, and US3 exists to catch the
  cases where that belief is wrong. When it does, FR-016 governs: restore first,
  report the finding, and let the author decide — never quietly rewrite the
  justification to fit what failed.
- **A verification that cannot fail is not a verification.** Because the author
  holds broad authority on the subscription, almost any command run by hand will
  succeed regardless of what the identity can do. Any check that does not
  distinguish the two is worthless here, which is why FR-004a requires the
  negative control rather than merely a passing result.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workspace identity MUST NOT hold any permission scoped to the
  resource group or above.
- **FR-002**: Every permission the workspace identity holds MUST be scoped to
  the single resource it applies to.
- **FR-003**: Every permission the workspace identity holds MUST be declared in
  the infrastructure template. This applies to all of them, not only to the one
  being removed: a permission the identity keeps MUST be taken out of the form
  the platform created it in and recreated under the template's ownership, so
  that no permission remains whose existence is visible only in the live
  environment.
- **FR-004**: Each declared permission MUST correspond to a need this project
  can state in one sentence, referring to something the environment actually
  does today. A permission justified only by a capability that has not been
  built yet MUST NOT be granted, even where that capability is already scheduled
  and the permission would predictably be needed again soon. The expected cost of
  this — an authorization failure during a later exercise — is accepted, and is
  covered by the reversal required in FR-012.
- **FR-004a**: The evidence that the workspace still works MUST come from an
  operation the service performs with its own identity, not from a command
  authenticated as the author. It MUST be paired with a negative control: the
  same operation has to fail when the permission it depends on is absent. If no
  such operation exists at this stage of the project, that MUST be reported as a
  limit of the verification rather than replaced by a command that appears to
  prove the point without doing so.
- **FR-005**: No permission the identity holds MAY confer wildcard authority
  over a resource type, the ability to create or delete resources, or the
  ability to alter the access configuration of the resource it applies to.
- **FR-006**: Each declared permission MUST be identified by a name the template
  derives deterministically from the deployment context, so that redeploying the
  unchanged template produces no change.
- **FR-007**: The template MUST identify the workspace identity by reference to
  the workspace declared in the same template, never by a literal identifier
  pasted in from the live environment.
- **FR-008**: The template MUST contain no literal subscription, tenant, or
  resource group identifier.
- **FR-009**: This feature MUST NOT declare any new Azure resource. It MUST NOT
  modify the configuration of the already-deployed resources, **with two named
  exceptions on the workspace itself**, both authorized by the author on
  2026-08-07 after the dry run revealed them:
  - the mode by which the workspace's system data stores authenticate, changed
    from account keys to its own identity — without which the least-privilege
    reduction would remove a permission the workspace still relies on;
  - the setting that lets the platform grant this identity authority over the
    whole resource group, turned off — the supported way to stop the platform
    re-granting what this feature removes.

  Both are changes this feature exists to make possible, not incidental drift.
  No other property of any resource may change, and no resource may be added or
  removed.
- **FR-010**: This feature MUST NOT introduce any secret, key, or connection
  string, and MUST NOT weaken the identity-based access model already in place.
- **FR-011**: This feature MUST NOT grant permissions to any principal other
  than the workspace identity.
- **FR-012**: The deployment runbook MUST record which permission was removed,
  what it allowed, which future capabilities are expected to need it, and the
  exact command that restores it.
- **FR-013**: The removal of a permission the template does not declare MUST be
  recorded as an explicit, separately authorized step, not left as an implied
  consequence of deploying the template.
- **FR-014**: The capability version used for each declared permission MUST be
  verified as current against the live provider before it is committed, per
  project principle II.
- **FR-015**: The change MUST pass a local template build and a dry run against
  the live environment before it is proposed for commit, and the effective
  permissions MUST be re-checked independently after deployment.
- **FR-016**: If verification shows the workspace has lost a permission it
  needed, the missing permission MUST be restored immediately using the recorded
  reversal, and the feature MUST stop for the author to decide how to proceed.
  The environment MUST NOT be left in a non-working state while the cause is
  investigated, and a permission MUST NOT be re-granted and then retroactively
  justified as necessary — a failure of this kind is reported as a finding, not
  absorbed as a requirement.

### Key Entities

- **Workspace identity**: the platform-managed identity belonging to the machine
  learning workspace. It is the only principal this feature grants anything to.
  It exists already and is not created, replaced, or reconfigured here.
- **Permission grant**: the association of one identity, one set of allowed
  operations, and one scope. It is control-plane metadata, carries no cost, and
  is the only kind of thing this feature creates or removes.
- **Scope**: the resource a permission applies to. This feature moves every
  grant from the resource group down to an individual resource.
- **Storage account** (existing): holds the workspace's data and artifacts. The
  identity needs to read and write the data it stores there.
- **Secret store** (existing): holds the workspace's secrets. The identity needs
  to use the secrets kept there; it does not need to govern who else can.
- **Telemetry resources** (existing): receive the workspace's operational logs.
  Whether the identity needs any permission on them at all is determined during
  planning, and none is granted unless a need can be stated.

## Success Criteria *(mandatory)*

Every criterion below is settled by the output of a command. None depends on
reading the change and forming a judgement.

### Measurable Outcomes

- **SC-001**: The local template build completes with zero errors and zero
  warnings.
- **SC-002**: The dry run against the live environment shows **exactly two
  entries to create, both of them permission grants**, nothing to delete, and no
  resource change beyond those reported by a **control run** — the same dry run
  against the previous, unchanged template.

  The control is what makes this checkable. A dry run of the *unchanged,
  already-deployed* template reports two resources to modify, because the
  template declares a subset of the properties the provider maintains and the
  tool renders the rest as removals. Its own output warns that results may
  contain false positives. A criterion demanding "nothing to modify" is
  therefore unsatisfiable by any template here, and would have failed a correct
  change. What must be zero is the *difference* this feature introduces, not the
  absolute count.
- **SC-003**: After deployment, enumerating the permissions held by the
  workspace identity returns **zero** grants scoped to the resource group or
  above.
- **SC-004**: After deployment, the set of permissions the identity holds is
  exactly the set the template declares — no permission is held that the
  template does not declare, and none is declared that the identity does not
  hold.
- **SC-005**: After deployment, no permission the identity holds allows creating
  or deleting resources, and none allows changing the access configuration of
  the resource it is scoped to.
- **SC-006**: After deployment, an operation carried out by the service under
  its own identity — against the storage account and against the secret store —
  completes without an authorization failure, **and** the same operation is
  observed to fail when the permission it depends on is withheld. A command
  authenticated as the author does not satisfy this criterion: it would pass
  whether or not the identity retained any permission at all.
- **SC-007**: After deployment, the environment contains exactly the same
  resources, with the same names, as the inventory captured before the change —
  nothing added, nothing removed.

  The reference is the captured baseline, not a fixed count. Feature 001 recorded
  five resources; the inventory taken at the start of this feature found **six**.
  The extra one is a notification group the platform created by itself ten
  minutes after the workspace, which no template declares. It carries no charge,
  it is outside this feature's scope to remove (FR-009 forbids touching the
  deployed resources), and it is recorded here because a criterion that named the
  number five would now fail for a reason having nothing to do with this change.
- **SC-008**: Redeploying the unchanged template a second time produces a dry
  run reporting **no permission grant to create** and no change beyond the
  control run's. The two declared grants must show as unchanged, proving their
  names are derived deterministically rather than regenerated. As with SC-002,
  the persistent property noise is measured against the control, not required to
  be absent.
- **SC-009**: The recurring cost added by this feature is **$0**. Permission
  grants are control-plane metadata and are not billed, and no resource changes
  its service tier.
- **SC-010**: Every step of the recorded reversal is a runnable command, and the
  count of removed permissions matches the count of restore commands written
  down.
- **SC-011**: The environment is left working at the end of the feature,
  whatever the outcome. Re-running the verification of SC-006 as the last action
  succeeds. The only period in which the identity is deliberately short of a
  permission is the negative control required by SC-006, which is reverted
  immediately and whose revert is itself confirmed by re-running the check.

## Assumptions

- The five deployed resources are correctly configured and are not changed by
  this feature; only the permissions pointing at them change.
- Nothing is currently running against this environment — no job, no endpoint,
  no scheduled work — so a brief interruption while a permission changes hands
  is harmless. This is what makes both the ownership transfer and the
  deliberate negative control of SC-006 acceptable to perform against a live
  environment rather than a copy.
- The author holds enough authority on the subscription to create and remove
  permission grants. Verified before this specification was written; recorded
  here because a reader with only the ability to deploy resources cannot carry
  out this feature.
- The permission grants the platform created were made at workspace creation by
  the platform itself, not by the author. Nothing depends on them that the
  author has configured by hand.
- Reducing the identity's authority is reversible: a permission that turns out
  to be needed can be granted again, and the cost of discovering this is a
  failed operation with a clear authorization error rather than data loss.
- The reduction is judged against what the environment does today. It is
  expected to need revisiting when compute, a container registry, or an endpoint
  is introduced, and that revisit is a separate feature.
- Deployment of the resulting template is a separate, explicitly authorized
  action, and every commit is proposed to the author with a diff rather than
  performed automatically, per project principle III.

## Out of Scope

- Any new Azure resource of any kind.
- Any compute target, endpoint, or container registry.
- Any change to the configuration of the five resources already deployed.
- Permissions for any principal other than the workspace identity — in
  particular, the deployment identity a continuous integration pipeline would
  need is a separate concern and a separate feature.
- Custom permission definitions authored from scratch. This feature selects from
  what the platform already offers; authoring a bespoke definition is a
  different exercise with a different cost of maintenance.
- Network-level restrictions, private endpoints, and customer-managed keys.
  These also narrow access, but by a different mechanism and at a different
  cost.
