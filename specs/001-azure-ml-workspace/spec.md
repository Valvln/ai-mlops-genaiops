# Feature Specification: Azure ML Workspace in the shared infrastructure template

**Feature Branch**: `001-azure-ml-workspace`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Add a minimal Azure ML workspace to the existing
Bicep template, reusing the storage account and key vault already defined,
without provisioning a Container Registry or any compute at this stage."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Declare a machine learning workspace on top of the existing foundation (Priority: P1)

The project author already maintains a single infrastructure template that
declares the shared storage account and key vault for AI-300 practice. They now
want that same template to describe a machine learning workspace, so that the
whole learning environment is expressed in one reviewable source file instead of
being half-declared and half-created by hand in the portal.

**Why this priority**: Without the workspace itself, none of the other AI-300
operationalization exercises (jobs, models, endpoints) have a home. This is the
foundational slice; everything else in the feature only refines it.

**Independent Test**: Build the template locally and inspect the generated
output. The workspace appears as a declared resource, wired to the pre-existing
storage account and key vault by reference rather than by copied identifiers.
Delivers value on its own: the author now has a single source of truth for the
learning environment.

**Acceptance Scenarios**:

1. **Given** the template already declares a storage account and a key vault,
   **When** the author builds the template locally, **Then** the build succeeds
   and the output describes a machine learning workspace alongside the existing
   resources.
2. **Given** the workspace declaration, **When** the author inspects how it
   links to storage and secret storage, **Then** those links are derived from
   the resources declared in the same template, not from values pasted in by
   hand.
3. **Given** the author supplies no workspace name, **When** the template is
   built, **Then** a deterministic name is derived from the target resource
   group so that two people building the same template into different resource
   groups do not collide.

---

### User Story 2 - Keep the environment inside the free-trial budget (Priority: P2)

The author is working on an Azure free trial and treats cost as a hard
constraint. The workspace must be declared in the cheapest configuration that
still supports the exam objectives, and must not silently pull in billable
companions.

**Why this priority**: Cost discipline is a non-negotiable project principle. A
workspace that quietly provisions a container registry or compute would breach
it, so this constraint is inseparable from the workspace itself — but the
workspace still has to exist first, hence P2.

**Independent Test**: Review the built output for billable resources. No
container registry is declared or requested, no compute target of any kind is
declared, and the workspace is set to the entry-level tier. Verifiable purely by
reading the generated template, with no deployment.

**Acceptance Scenarios**:

1. **Given** the workspace declaration, **When** the built output is inspected,
   **Then** it contains no container registry association whatsoever.
2. **Given** the workspace declaration, **When** the built output is inspected,
   **Then** no compute instance or compute cluster is declared.
3. **Given** the workspace declaration, **When** its service tier is inspected,
   **Then** it is the entry-level tier rather than a production tier.
4. **Given** the telemetry resources the workspace depends on, **When** their
   configuration is inspected, **Then** they are consumption-based, use default
   retention, and are expected to stay within the free monthly allowance at the
   project's usage level.

---

### User Story 3 - Access the environment through a managed identity (Priority: P2)

The author wants the workspace to authenticate to the storage account and key
vault through its own platform-managed identity, so that role-based access
control — an explicit AI-300 objective — can be practised later without any
secret being stored or rotated by hand.

**Why this priority**: This is the identity-management learning objective the
feature exists to serve, and the key vault in the template is already configured
for role-based access rather than access policies. It is separable from US1 (a
workspace can exist without an identity) but not optional for the exercise.

**Independent Test**: Inspect the workspace declaration for an identity of the
system-assigned kind. Delivers value independently: once the environment is
deployed, role assignments can be granted to that identity without changing the
template's other resources.

**Acceptance Scenarios**:

1. **Given** the workspace declaration, **When** its identity configuration is
   inspected, **Then** a system-assigned managed identity is requested.
2. **Given** the deployed workspace (future work, outside this feature),
   **When** an administrator grants it a role on the storage account, **Then**
   no secret or connection string has to be created to make that access work.

---

### User Story 4 - Hand the workspace identifiers to downstream work (Priority: P3)

Later exercises — CLI commands, pipeline definitions, follow-up templates — need
to address the workspace without the author looking it up in the portal each
time.

**Why this priority**: Pure convenience for subsequent milestones. The feature
is still useful without it, so it ranks last.

**Independent Test**: Build the template and confirm that both the workspace's
name and its full resource identifier are exposed as outputs.

**Acceptance Scenarios**:

1. **Given** a successful build, **When** the template's outputs are inspected,
   **Then** the workspace name and the workspace resource identifier are both
   published.

---

### Edge Cases

- **Name length and character rules**: a generated workspace name must stay
  inside the naming rules for the resource type (length, allowed characters).
  The prefix plus the derived uniqueness suffix must not overflow that limit.
- **Telemetry dependency**: classic, standalone application-monitoring resources
  are retired; current ones are backed by a log workspace. A telemetry resource
  declared without that backing would still build locally but be rejected at
  deployment time. The backing log workspace is therefore in scope — see
  Resolved Decisions, D1.
- **API version drift**: the resource type version named in the request may no
  longer be the current one. It must be verified against the live provider
  before it is written into the template, per project principle II.
- **Redeployment into a resource group that already holds a workspace**: the
  derived name is stable per resource group, so a rebuild targets the same
  workspace rather than creating a second one.
- **Key vault purge protection**: the existing key vault has purge protection
  enabled, so a workspace bound to it cannot be fully torn down and recreated
  under the same key vault name within the retention window. Relevant to any
  later teardown exercise, not to this template-authoring task.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The infrastructure template MUST declare a machine learning
  workspace in addition to the resources it already declares.
- **FR-002**: The workspace name MUST be configurable, and MUST default to a
  value derived deterministically from the target resource group, carrying a
  project-specific prefix so it is recognisable among other resources.
- **FR-003**: The workspace MUST reference the storage account and the key vault
  already declared in the same template, by reference to those declarations
  rather than by literal identifiers.
- **FR-004**: The template MUST declare an application-monitoring resource for
  the workspace's basic logging needs, configured for consumption-based billing.
- **FR-004a**: The template MUST declare the backing log workspace that the
  application-monitoring resource stores its data in, and the monitoring
  resource MUST reference it. It MUST use the default retention and the
  consumption-based pricing tier, so that it stays inside the free monthly
  ingestion allowance at this project's volume.
- **FR-005**: The workspace MUST request a system-assigned managed identity.
- **FR-006**: The workspace MUST be declared at the entry-level service tier.
- **FR-007**: The workspace MUST NOT be associated with a container registry,
  and MUST NOT cause one to be provisioned automatically.
- **FR-008**: The template MUST NOT declare any compute target as part of this
  feature.
- **FR-009**: The new resources MUST carry the same project and environment tags
  already used by the existing resources.
- **FR-010**: The template MUST publish the workspace name and the workspace
  resource identifier as outputs.
- **FR-011**: The template MUST contain no hardcoded subscription, tenant, or
  resource-group identifiers; such values MUST be derived from the deployment
  context.
- **FR-012**: The resource type version used for each new resource MUST be
  verified as current against the live Azure provider before it is committed to
  the template, and MUST be the latest generally-available version — never a
  preview one, and never a stale one carried over from an example.
- **FR-013**: The change MUST be validated by a local template build only. No
  deployment to Azure is performed as part of this feature.

### Key Entities

- **Machine learning workspace**: the top-level container for the project's ML
  assets. Bound to a storage account (data and artifacts), a key vault
  (secrets), and an application-monitoring resource (logs). Owns a
  platform-managed identity. Deliberately not bound to a container registry.
- **Application monitoring resource**: receives the workspace's basic
  operational logs. Consumption-billed, sized to stay inside the free monthly
  allowance. Stores its data in the log workspace below.
- **Log workspace**: the data store behind the application monitoring resource.
  Declared only because current application monitoring requires it; carries no
  independent purpose in this feature and is expected to ingest well under the
  free monthly allowance.
- **Storage account** (existing): already declared in the template; reused, not
  duplicated.
- **Key vault** (existing): already declared in the template with role-based
  access enabled; reused, not duplicated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The local template build completes with zero errors.
- **SC-002**: The generated template declares exactly 5 resources — the two
  pre-existing ones (storage account, key vault) plus the log workspace, the
  application-monitoring resource, and the machine learning workspace — with no
  resource the author did not ask for.
- **SC-003**: A search of the generated template for a container registry
  association returns nothing.
- **SC-004**: A search of the generated template for literal subscription,
  tenant, or resource-group identifiers returns nothing.
- **SC-005**: The generated template exposes both the workspace name and the
  workspace resource identifier as outputs.
- **SC-006**: The recurring cost added by this feature, if the template were
  deployed at the project's usage level, is $0 — no resource in it is billed
  outside a free allowance at that volume.
- **SC-007**: The whole feature is verifiable offline: every criterion above can
  be checked without a single Azure deployment.

## Assumptions

- The existing storage account and key vault are suitable for the workspace as
  currently configured, and are not modified by this feature.
- The key vault's existing role-based access configuration is the intended
  access model; no access policies are added.
- A single learning environment is targeted. Multi-environment parameterisation
  (dev/test/prod) is out of scope.
- Networking is left at the service default. No private endpoints, no network
  isolation, no customer-managed keys — all of which would add cost or
  complexity beyond the current exam objective.
- Compute, data stores, endpoints, and registry are all deferred to later
  features; this one stops at the workspace shell.
- The application-monitoring resource and its backing log workspace are assumed
  to remain within their free monthly ingestion allowance at this project's
  usage level, making them effectively free.
- Deployment of the resulting template is a separate, explicitly authorized
  action and is not part of this feature.
- The commit is proposed to the project author with a diff and is never
  performed automatically, per project principle III.

## Resolved Decisions

Both decisions below were raised with the project author during specification
and answered by them; neither was assumed.

### D1 — The backing log workspace is in scope (resource count is 5, not 4)

Standalone (classic) application-monitoring resources are retired; current ones
are workspace-based and store their data in a log workspace. Declaring the
monitoring resource without that backing would produce a template that builds
locally but is rejected at deployment.

**Decision**: declare the log workspace. The original "exactly 4 resources"
criterion becomes "exactly 5" (**SC-002**). The intent behind that criterion —
*nothing gets provisioned that the author did not ask for* — is preserved: the
log workspace is a required dependency, not a convenience addition.

**Cost impact**: none. Ingestion is billed per GB with a free monthly allowance
this project's volume stays well inside, so **SC-006** ($0 recurring) is
unaffected.

### D2 — Use the current generally-available API version

The version named in the original request (`2024-10-01`) was checked against the
live provider: still supported, but no longer current. The latest
generally-available version at the time of writing is `2026-05-01`.

**Decision**: use the current generally-available version rather than the one
carried over from the request, in line with project principle II (API versions
are verified, never assumed). The exact version strings for every resource are
re-verified during planning and recorded there.
