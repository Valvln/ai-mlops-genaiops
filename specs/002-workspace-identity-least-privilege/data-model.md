# Phase 1 — Data model

> **Describes an intended state that was not reached, 2026-08-08.** The target
> below is two grants; the identity holds seven, six of them maintained by the
> platform. The transition and ordering were executed as written and are
> accurate as a record of what was done. See [research.md](research.md) R10.


The only entity this feature creates or destroys is a **role assignment**: the
association of one principal, one role definition, and one scope. It is
control-plane metadata and carries no cost.

## The single principal

| Attribute | Value |
| --- | --- |
| Principal | system-assigned managed identity of the ML workspace |
| Object id | `85e8321f-1e51-42cb-8ced-7fca9b51498b` (observed; never written into the template) |
| Referenced in the template as | `mlWorkspace.identity.principalId` |
| Principal type | `ServicePrincipal` |

The object id appears in this document because a reader needs it to verify the
result by hand. It must **not** appear in the template — FR-007 requires the
identity to be reached by reference to the workspace declared alongside it.

## Current state — four grants, none declared

| # | Role | Scope | Assignment name | Origin |
| --- | --- | --- | --- | --- |
| C1 | Azure AI Administrator | resource group | `d37b8682-e1cf-47b4-85af-5face2834f53` | platform, at workspace creation |
| C2 | Storage Blob Data Contributor | storage account | platform-generated | platform |
| C3 | Storage File Data Privileged Contributor | storage account | platform-generated | platform |
| C4 | Key Vault Administrator | key vault | platform-generated | platform |

## Target state — two grants, both declared

| # | Role | Scope | Name | The need, in one sentence |
| --- | --- | --- | --- | --- |
| T1 | Storage Blob Data Contributor | storage account | `guid(storage.id, workspace.id, roleDefId)` | The workspace's two blob datastores are identity-based, so this is the only way the service can read or write its own artifacts. |
| T2 | Key Vault Secrets User | key vault | `guid(vault.id, workspace.id, roleDefId)` | The workspace reads the secrets it keeps in its own vault; it has no need to write any, and no need to govern who else may read them. |

Nothing is granted on Application Insights, on the Log Analytics workspace, or
at resource-group scope.

## Transition

| Grant | Action | Why |
| --- | --- | --- |
| C1 → gone | delete | No need can be named for it. It is the whole point of the feature. |
| C2 → T1 | delete, then re-create from the template | Same role and scope, so the template cannot add it alongside; ownership transfers by replacement. |
| C3 → gone | delete | Backs the two file datastores, which only a compute target mounts. There is no compute. **Highest-risk removal in this feature.** |
| C4 → T2 | create T2, then delete C4 | Different role definitions, so both can exist briefly. Creating first means the identity never lacks vault **read** access. Write access and access governance are dropped deliberately — see the note below. |

### Ordering, and where the gaps are

The order below is chosen to keep every gap as short as possible and to leave
none open at the end of a session.

1. **Delete C2.** The identity now has no blob access. This is the only
   unavoidable gap, because T1 cannot be created while C2 exists.
2. **Deploy the template.** Creates T1 and T2. The blob gap closes here; the
   vault is covered by C4 throughout, since C4 is still in place.
3. **Delete C4, C3, C1.** T2 already covers reading the vault, so deleting C4
   opens **no read gap**. It does drop the ability to write secrets and to
   govern who else may access the vault — deliberately, and on an inference that
   [research.md](research.md) R6 records as unverified: the vault's contents
   could not be listed, so "the workspace has nothing to write" rests on the
   absence of any credential-carrying datastore or connection rather than on
   direct observation. If that inference is wrong, the symptom is an
   authorization error and the fix is widening T2 to secret write — not
   restoring C4. C3 and C1 have no replacement by design.
4. **Verify**, then leave the environment working.

The gap in step 1 lasts as long as a deployment — roughly a minute on the
evidence of feature 001. Nothing is running against this environment, so it is
expected to be unobservable.

## Validation rules

| Rule | Source | How it is checked |
| --- | --- | --- |
| Assignment name is a GUID derived from scope + workspace + role | FR-006, R8 | redeploy shows no change (SC-008) |
| Principal is the workspace, by reference | FR-007 | template contains no object id |
| Scope is a single resource, never the group | FR-001, FR-002 | enumerate assignments, check scope depth (SC-003) |
| No wildcard, create/delete, or access-governance authority | FR-005 | inspect the two role definitions (SC-005) |
| Every held permission is declared, and vice versa | FR-003 | compare the two sets (SC-004) |
| `principalType` is declared | R9 | present in the template |

## What this feature does not touch

The five deployed resources keep their configuration exactly as feature 001 left
it. No resource is added or removed, no service tier changes, no secret is
created, and no principal other than the workspace identity is granted anything.
