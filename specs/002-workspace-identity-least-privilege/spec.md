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

**Independent Test**: after the reduction, run a command that makes the
workspace exercise its identity against a resource it still has permission for,
and confirm it completes without an authorization failure.

**Acceptance Scenarios**:

1. **Given** the reduction has been applied, **When** the workspace is queried,
   **Then** it reports itself as successfully provisioned, exactly as before.
2. **Given** the reduction has been applied, **When** an operation that requires
   the workspace identity to reach the storage account is performed, **Then** it
   succeeds without an authorization error.
3. **Given** the reduction has been applied, **When** an operation that requires
   the workspace identity to reach the secret store is performed, **Then** it
   succeeds without an authorization error.

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
  new one created. Between the two the identity lacks that permission. Nothing
  is running against this environment, so the window is expected to be harmless
  — but the ordering must be deliberate rather than incidental.
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
  cases where that belief is wrong.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workspace identity MUST NOT hold any permission scoped to the
  resource group or above.
- **FR-002**: Every permission the workspace identity holds MUST be scoped to
  the single resource it applies to.
- **FR-003**: Every permission the workspace identity holds MUST be declared in
  the infrastructure template.
- **FR-004**: Each declared permission MUST correspond to a need this project
  can state in one sentence, referring to something the environment actually
  does today. A permission justified only by a capability that has not been
  built yet MUST NOT be granted.
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
- **FR-009**: This feature MUST NOT declare any new Azure resource, and MUST NOT
  modify the configuration of any of the five resources already deployed.
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
- **SC-002**: The dry run against the live environment reports zero resources
  created, zero deleted, and zero modified. The only entries it shows are
  permission grants.
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
- **SC-006**: After deployment, the workspace reports itself as successfully
  provisioned, and an operation that requires the identity to reach the storage
  account and the secret store completes without an authorization failure.
- **SC-007**: After deployment, the environment still contains exactly the same
  five resources, with the same names, as before the change.
- **SC-008**: Redeploying the unchanged template a second time produces a dry
  run reporting no change whatsoever.
- **SC-009**: The recurring cost added by this feature is **$0**. Permission
  grants are control-plane metadata and are not billed, and no resource changes
  its service tier.
- **SC-010**: Every step of the recorded reversal is a runnable command, and the
  count of removed permissions matches the count of restore commands written
  down.

## Assumptions

- The five deployed resources are correctly configured and are not changed by
  this feature; only the permissions pointing at them change.
- Nothing is currently running against this environment — no job, no endpoint,
  no scheduled work — so a brief interruption while a permission changes hands
  is harmless.
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
