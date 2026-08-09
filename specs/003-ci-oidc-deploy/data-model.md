# Data model: objects this feature creates

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

No application data. The "model" here is the set of objects created across three
different control planes, which is worth laying out because the split is not
obvious and drives the task order.

## Objects

### 1. Application registration — `ai300-github-deploy`

Entra directory object. Not an ARM resource; cannot be expressed in Bicep (R8).

| Field | Value |
| --- | --- |
| Display name | `ai300-github-deploy` |
| Password credentials | **zero, always** (FR-002) |
| Certificate credentials | **zero, always** (FR-002) |
| Sign-in audience | this tenant only |

Its **application (client) id** is what gets stored as `AZURE_CLIENT_ID`.

### 2. Service principal

The directory's representation of the application inside this tenant. Its
**object id** is what a role assignment points at — not the client id, and
confusing the two produces a role assignment against a principal that does not
exist.

### 3. Federated identity credential

The trust condition. Attached to the application.

| Field | Value |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Subject | **read from an observed token**, expected `repo:Valvln@188171957/ai-mlops-genaiops@1324268843:environment:azure-deploy` |
| Audience | `api://AzureADTokenExchange` |

The subject is the field this feature is most likely to get wrong (R3): this
repository was created after the immutable-subject cutover, so the conventional
`repo:OWNER/REPO:...` form does not apply. It is copied from a token that was
actually issued, not typed from documentation.

**State transition worth naming**: before this object exists, every
authentication attempt fails — which is the state SC-004's refusals are captured
in. It is cheaper to record them then than to break the credential later to
reproduce them.

### 4. GitHub environment — `azure-deploy`

| Field | Value |
| --- | --- |
| Required reviewers | the author |
| Prevent self-review | **off** — one author, see R5 |
| Deployment branches | `main` only |

Both a GitHub control and half of the Entra trust condition: the environment name
appears inside the federated credential's subject, so entering the environment is
what makes the token exchangeable.

### 5. Custom role definition — `AI300 CI Deployer (rg-ai300-test01)`

ARM resource, declared in `infra/ci-identity.bicep`. Contents and provenance:
[contracts/role-definition.md](contracts/role-definition.md).

`assignableScopes` holds one resource group id.

### 6. Role assignment

Binds the role to the service principal at `rg-ai300-test01`. Declared in the
same template, name derived with `guid()` so redeployment is idempotent —
the mechanics feature 002 established and which are reused here.

### 7. Probe resource group — `rg-ai300-probe`

Empty, holds nothing, exists only so probe P2 has a **named** target that
exists (FR-017b). Free. Removed by the reversal.

## Where each object lives

| Control plane | Objects | Created by |
| --- | --- | --- |
| Entra (directory) | 1, 2, 3 | author, `az ad` commands |
| GitHub | 4, plus the three stored identifiers | author, `gh` / repository settings |
| Azure ARM | 5, 6, 7 | author — 5 and 6 via `ci-identity.bicep`, 7 by command |

**Nothing in this table is created by continuous integration.** CI deploys
`main.bicep` and nothing else; it cannot create the authority it runs with, and
FR-005 keeps it unable to.

## Creation order

The order is forced by the dependencies, and getting it wrong wastes a gate
approval:

1. Application → service principal (object id needed by step 5)
2. GitHub environment (its name is needed by step 4)
3. A workflow run that prints the token's `sub` claim — **fails to authenticate,
   by design**, and yields both the subject and SC-004's first refusal
4. Federated credential, from the observed subject
5. `ci-identity.bicep` deployed by the author → role definition and assignment
6. Deploying workflow run → discovery and verification of the operation set

Steps 3 and 6 are where the two observational passes happen. Neither can be
short-circuited without abandoning FR-006a.

## Evidence artifacts

Not objects in any control plane, but the deliverables the exit criterion names.
Stored under `specs/003-ci-oidc-deploy/evidence/`.

| Artifact | Satisfies |
| --- | --- |
| Deployment record id of the green run | SC-001 |
| Inventory before and after | SC-002 |
| Four captured authorization refusals | SC-003 |
| Three captured authentication refusals | SC-004 |
| Run history for a pull request | SC-005 |
| Credential enumeration returning empty | SC-006 |
| Withdraw / fail / restore / succeed run pair | SC-007 |
| Cost report over the feature's days | SC-008 |
| Reversal commands | SC-009 |
