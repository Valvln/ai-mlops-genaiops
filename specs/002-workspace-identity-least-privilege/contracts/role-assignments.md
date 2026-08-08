# Contract — declared role assignments

> **The blob assignment in this contract cannot be deployed, 2026-08-08.** The
> platform recreates its own grant of the same role at the same scope, so the
> declaration is rejected as a duplicate. Only the key vault assignment is in
> `main.bicep`. See [research.md](../research.md) R10.


The interface this feature exposes is the template's declaration of what the
workspace identity may do. This document fixes that contract so the
implementation has nothing left to invent and the review has something exact to
check against.

## Template additions

Two resources are added to `infra/main.bicep`. Nothing existing is modified.

### Role definition references

Role definitions are subscription-level resources and are referenced, never
declared:

```bicep
// Built-in role definition identifiers, resolved against the live tenant
// (see research.md R2). They are stable across tenants.
var storageBlobDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)
var keyVaultSecretsUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)
```

`subscriptionResourceId` is what keeps FR-008 satisfied: the subscription
identifier comes from the deployment context rather than from a literal.

### T1 — blob data access on the storage account

```bicep
resource storageBlobRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, mlWorkspace.id, storageBlobDataContributorRoleId)
  properties: {
    roleDefinitionId: storageBlobDataContributorRoleId
    principalId: mlWorkspace.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
```

### T2 — secret read access on the key vault

```bicep
resource keyVaultSecretsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, mlWorkspace.id, keyVaultSecretsUserRoleId)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: mlWorkspace.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
```

## Contract invariants

| Invariant | Consequence if broken |
| --- | --- |
| `scope` is a resource symbol, never omitted | omitting it targets the resource group, defeating the entire feature |
| `name` is `guid()` over exactly (scope id, workspace id, role id) | redeployment either conflicts or creates a duplicate; SC-008 fails |
| `principalId` comes from `mlWorkspace.identity.principalId` | an object id pasted in as a literal breaks FR-007 and the clean-rebuild case |
| `principalType` is `'ServicePrincipal'` | intermittent `PrincipalNotFound` on a rebuild, when the identity is newer than the directory replica |
| role identifiers are referenced via `subscriptionResourceId` | a literal subscription id in the template breaks FR-008 |
| exactly two assignments are declared | a third means a permission was granted without a stated need |

## Commands that are part of the contract

These are the steps the template cannot perform. Deployment adds and updates; it
never removes what it was not told about, so each removal below is a deliberate,
separately authorized act (FR-013).

Every one of them requires the assignment's own name, which must be read from
the live environment first rather than guessed.

```bash
export PATH="/usr/local/bin:$PATH"
RG=rg-ai300-test01
MI=85e8321f-1e51-42cb-8ced-7fca9b51498b

# What the identity holds right now, with the names needed to remove anything
az role assignment list --all --assignee "$MI" \
  --query "[].{name:name, role:roleDefinitionName, scope:scope}" -o table
```

### Removals

```bash
# C2 — blob access, removed so the template can take ownership of it (step 1)
az role assignment delete --assignee "$MI" \
  --role "Storage Blob Data Contributor" \
  --scope "$(az storage account show -n ai300st2mgou37pfmjou -g $RG --query id -o tsv)"

# C4 — vault administration, superseded by T2 (step 3, after the deployment)
az role assignment delete --assignee "$MI" \
  --role "Key Vault Administrator" \
  --scope "$(az keyvault show -n ai300kv2mgou37pfmjou -g $RG --query id -o tsv)"

# C3 — file share access, dropped with no replacement (step 3)
az role assignment delete --assignee "$MI" \
  --role "Storage File Data Privileged Contributor" \
  --scope "$(az storage account show -n ai300st2mgou37pfmjou -g $RG --query id -o tsv)"

# C1 — the resource-group-wide grant, the point of the feature (step 3)
az role assignment delete --assignee "$MI" \
  --role "Azure AI Administrator" \
  --scope "$(az group show -n $RG --query id -o tsv)"
```

### Reversal — the way back, required by FR-012

Each removal above has exactly one restore command. Nothing here depends on a
value that was not written down.

```bash
SA=$(az storage account show -n ai300st2mgou37pfmjou -g $RG --query id -o tsv)
KV=$(az keyvault show -n ai300kv2mgou37pfmjou -g $RG --query id -o tsv)
RGID=$(az group show -n $RG --query id -o tsv)

# Restore C1 — needed if the workspace must provision compute, a container
# registry, or an endpoint on demand
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure AI Administrator" --scope "$RGID"

# Restore C3 — needed as soon as a compute target mounts workspacefilestore
# or workspaceworkingdirectory
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage File Data Privileged Contributor" --scope "$SA"

# Restore C4 — needed only if the workspace must manage vault access itself;
# prefer widening T2 to "Key Vault Secrets Officer" if the need is merely to
# write secrets
az role assignment create --assignee-object-id "$MI" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Administrator" --scope "$KV"
```

`--assignee-object-id` with an explicit principal type is used rather than
`--assignee`, which resolves the principal through a directory lookup that a
non-administrator may not be permitted to perform.

## Verification contract

| Criterion | Command | Passes when |
| --- | --- | --- |
| SC-003 | `az role assignment list --all --assignee $MI --query "[?!contains(scope,'/providers/Microsoft.')]"` | returns `[]` — no grant above a single resource |
| SC-004 | `az role assignment list --all --assignee $MI --query "length(@)"` | returns `2` |
| SC-007 | `az resource list -g $RG --query "length(@)"` | returns `5` |
| SC-002 | `az deployment group what-if -g $RG --template-file infra/main.bicep` | exactly two entries, both permission grants to create; nothing to delete, nothing to modify, nothing else to create |
| SC-008 | the same command, re-run after the deployment with no edits | no change of any kind |
| SC-006 | see [quickstart.md](../quickstart.md) | service-side probe passes, and its negative control fails |
