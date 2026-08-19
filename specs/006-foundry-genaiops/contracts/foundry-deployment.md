# Contract: `infra/foundry.bicep` deployment

What the template must create, what it must never create, and what proves each
before it's proposed for a real deployment.

## Inputs

| Parameter | Default | Constraint |
| --- | --- | --- |
| `location` | `'swedencentral'` | not overridable to `northeurope` by this template — that's `main.bicep`'s region (FR-002) |
| Resource group | `rg-ai300-foundry`, created by the author before this template runs | not created by the template itself, matching `main.bicep`'s own pattern (`az group create` is a runbook step, not a Bicep resource) |

## What it MUST create (exactly these, per FR-001–FR-003 and data-model.md)

1. One `Microsoft.CognitiveServices/accounts`, kind `AIServices`.
2. One `accounts/projects` as its child.
3. One `accounts/deployments`, SKU `GlobalStandard` or `Standard` — never a
   PTU-family SKU name.
4. One `Microsoft.OperationalInsights/workspaces`.
5. One `Microsoft.Insights/components`, workspace-based against (4).
6. One `accounts/connections` and one `accounts/projects/connections`, both
   category `AppInsights`, targeting (5).
7. **Added during implementation, from a refusal — see tasks.md T012a.** One
   `Microsoft.Authorization/roleAssignments` granting the caller
   `Cognitive Services OpenAI User` on (1), conditional on a non-empty
   `callerPrincipalId` parameter. Without it the template deploys
   infrastructure nobody can call: the first request returned `401
   PermissionDenied` naming the missing data action, because Owner is a
   control-plane role and grants nothing on the Cognitive Services data plane.

## What it MUST NOT create

- A hub (`Microsoft.MachineLearningServices/workspaces`, kind `hub`) or
  anything the hub path would provision on its behalf (container registry,
  Key Vault, storage account) — FR-001.
- An Azure AI Search resource of any tier — FR-005.
- A deployment on any PTU-family SKU (`ProvisionedManaged`,
  `GlobalProvisionedManaged`, `DataZoneProvisionedManaged`) — FR-003.

## Pre-deployment checks (in order, all free)

1. `az provider show --namespace Microsoft.CognitiveServices --query
   registrationState` → `Registered` (already true as of this plan — R2).
2. `az cognitiveservices model list -l swedencentral` — reconfirm the chosen
   model's SKU availability (FR-004).
3. `az cognitiveservices usage list -l swedencentral` — reconfirm the chosen
   model's quota is nonzero (R4's lesson: availability in the catalog is not
   availability in this subscription).
4. `az bicep build --file infra/foundry.bicep` — exit 0, no output.
5. `az deployment group what-if --resource-group rg-ai300-foundry
   --template-file infra/foundry.bicep --parameters callerPrincipalId=<oid>` —
   reviewed by the author before the real run (FR-011). Against an empty
   resource group, expect **8 creates**: the seven objects above, with the
   `accounts/projects/connections` counting separately from the account-level
   one. (Written as 7 before implementation, when the role assignment was not
   yet known to be necessary.)

   Against a partially deployed group, what-if reports `Modify` on the account
   and project with `Delete` deltas for `properties.defaultProject`,
   `properties.associatedProjects`, `kind`, `properties.endpoints`,
   `properties.internalId` and `properties.isDefault`. **This is noise, and it
   was checked rather than tolerated**: those are provider-populated fields the
   template does not declare, what-if reports undeclared properties as
   deletions in Incremental mode, and all six were read back intact from the
   live resources after the deployment ran.

## Post-deployment verification

| Check | Command | Satisfies |
| --- | --- | --- |
| Deployment SKU is token-billed | `az cognitiveservices account deployment show -n <account> -g rg-ai300-foundry --deployment-name gpt-4.1-mini --query sku.name` | SC-001 |
| Nothing extra exists | `az resource list -g rg-ai300-foundry --query "[].type"` | SC-005 |
| At-rest cost is zero | Cost Management query, next day (deferred — see spec's Deferred Criteria) | SC-006 |

## Deletion (per spec constraint 4 — written before anything is created)

```bash
az group delete --name rg-ai300-foundry --yes
```

Removes all seven resources in one command; nothing in this feature survives
outside that resource group (no role assignment at subscription scope, no
soft-deleted resource with a retention lock — the Foundry account and
Application Insights don't carry the Key Vault's 90-day name-lock behaviour).
Verify with `az resource list -g rg-ai300-foundry` returning empty
(SC-007).
