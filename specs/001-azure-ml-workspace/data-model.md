# Phase 1 Data Model: Azure ML Workspace

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**:
2026-08-06

For an infrastructure feature the "data model" is the resource graph: what is
declared, how the pieces reference each other, and which properties are fixed by
the spec.

## Resource graph

```text
                     ┌──────────────────────────┐
                     │  storageAccount (exists) │──────┐
                     └──────────────────────────┘      │
                                                       │
                     ┌──────────────────────────┐      │  properties.storageAccount
                     │  kv (exists)             │──────┤  properties.keyVault
                     └──────────────────────────┘      │  properties.applicationInsights
                                                       │
  ┌───────────────┐        ┌────────────────────┐      ▼
  │ logAnalytics  │───────▶│ applicationInsights│──▶ ┌────────────────────┐
  │  (new)        │  Work  │  (new)             │    │ mlWorkspace (new)  │
  └───────────────┘ spaceId└────────────────────┘    │ + SystemAssigned   │
                                                     │   managed identity │
                                                     └────────────────────┘
                                                              ✗ containerRegistry
                                                              ✗ compute
```

Every arrow is a symbolic `.id` reference in Bicep, which makes ARM infer
`dependsOn`. No dependency is written by hand.

## Entities

### Log Analytics workspace (new)

| Attribute | Value | Source |
| --- | --- | --- |
| Type | `Microsoft.OperationalInsights/workspaces` | — |
| API version | `2025-07-01` | [research.md](./research.md) R3 |
| Name | derived from `uniqueString(resourceGroup().id)` | FR-002 pattern |
| Location | `location` parameter | existing template |
| `properties.sku.name` | `PerGB2018` | consumption-based, FR-004a |
| `properties.retentionInDays` | `30` | service default; free allowance |
| Tags | `project: ai300-prep`, `environment: learning` | FR-009 |

Exists only to back Application Insights (decision D1). It holds no independent
purpose.

### Application Insights component (new)

| Attribute | Value | Source |
| --- | --- | --- |
| Type | `Microsoft.Insights/components` | — |
| API version | `2020-02-02` | research.md R2 |
| Name | derived from `uniqueString(resourceGroup().id)` | FR-002 pattern |
| `kind` | `web` | required by the type |
| `properties.Application_Type` | `web` | required by the type |
| `properties.WorkspaceResourceId` | `logAnalytics.id` | D1 — mandatory since classic retirement |
| `properties.IngestionMode` | `LogAnalytics` | consistent with workspace-based mode |
| Tags | `project: ai300-prep`, `environment: learning` | FR-009 |

### Machine learning workspace (new)

| Attribute | Value | Source |
| --- | --- | --- |
| Type | `Microsoft.MachineLearningServices/workspaces` | — |
| API version | `2026-05-01` | research.md R1, verified in R4 |
| Name | `workspaceName` parameter | FR-002 |
| `identity.type` | `SystemAssigned` | FR-005 |
| `sku.name` / `sku.tier` | `Basic` / `Basic` | FR-006 |
| `properties.storageAccount` | `storageAccount.id` | FR-003 |
| `properties.keyVault` | `kv.id` | FR-003 |
| `properties.applicationInsights` | `applicationInsights.id` | FR-004 |
| `properties.containerRegistry` | **property absent entirely** | FR-007 |
| Tags | `project: ai300-prep`, `environment: learning` | FR-009 |

On `containerRegistry`: research R4 confirmed the property is optional under
this API version, so it is simply not written. Omission is stronger than an
explicit `null` — there is no key in the compiled JSON at all, which is exactly
what SC-003 greps for.

### Storage account and key vault (existing, unchanged)

Referenced by symbolic name only. This feature does not touch their
declarations. Worth noting for later work: the key vault already has
`enableRbacAuthorization: true`, which is what makes the workspace's managed
identity the right access path rather than access policies.

## Validation rules

| Rule | Enforced by |
| --- | --- |
| Workspace name 3–33 chars, alphanumeric plus hyphen | `ai300ml` + 13-char `uniqueString` = 20 chars (research R5) |
| Names unique per resource group | `uniqueString(resourceGroup().id)` is deterministic per group |
| No literal subscription or tenant id | all ids come from symbolic references and `subscription().tenantId` |
| No preview API versions | research.md R1–R3 |

## Out of scope

Compute targets, datastores beyond the default, online/batch endpoints,
container registry, private endpoints, customer-managed keys, and role
assignments. Role assignments in particular are the natural next feature: the
managed identity declared here is what they will attach to.
