# Data Model: Block 3 — Azure AI Foundry GenAIOps backbone

This feature has no application database. "Entities" here are the Azure
resources and repository artifacts the spec's Key Entities section names,
made concrete with the choices [research.md](./research.md) settled.

## Infrastructure entities

| Entity | ARM type | API version | Identity | Notes |
| --- | --- | --- | --- | --- |
| Foundry account | `Microsoft.CognitiveServices/accounts` | `2025-06-01` (R3) | `ai300fdry${uniqueString(resourceGroup().id)}` | kind `AIServices`, sku `S0`, location `swedencentral` |
| Foundry project | `Microsoft.CognitiveServices/accounts/projects` | `2025-06-01` (R3) | `block3-genaiops` | child of the account; name is stable, not `uniqueString`-suffixed — unique within the account is enough |
| Model deployment | `Microsoft.CognitiveServices/accounts/deployments` | `2025-06-01` (R3) | `gpt-4.1-mini` | sku `GlobalStandard`, capacity `1`; model `{format: OpenAI, name: gpt-4.1-mini, version: 2025-04-14}` (R4) |
| Log Analytics workspace | `Microsoft.OperationalInsights/workspaces` | matches `main.bicep`'s pinned version | `ai300fdrylaw${uniqueString(...)}` | trace/telemetry store underneath Application Insights |
| Application Insights | `Microsoft.Insights/components` | matches `main.bicep`'s pinned version | `ai300fdryappi${uniqueString(...)}` | workspace-based (`WorkspaceResourceId` → the Log Analytics workspace above); kind `web` |
| Account-level connection | `Microsoft.CognitiveServices/accounts/connections` | `2025-04-01-preview`, **not yet what-if'd** (R3, R6) | `${foundry account name}-appinsights` | category `AppInsights`, target = App Insights resource id, `authType: ApiKey`, credentials from the App Insights connection string |
| Project-level connection | `Microsoft.CognitiveServices/accounts/projects/connections` | same as above | same name pattern | mirrors the account-level connection at the project scope; this is the one the SDK/portal actually reads for project-scoped tracing |
| Resource group | `Microsoft.Resources/resourceGroups` | — | `rg-ai300-foundry` | `swedencentral`; everything above lives inside it; deleting it deletes everything this feature created (SC-007) |

**What's deliberately absent**: no hub (`Microsoft.MachineLearningServices/workspaces`,
kind `hub`), no container registry, no Key Vault, no storage account, no AI
Search. Nothing here is a dependency the account or project provisions on its
own — every row above is declared and owned by `infra/foundry.bicep`.

### Relationships

```
resource group (rg-ai300-foundry)
├── Foundry account
│   ├── Foundry project
│   │   └── project-level connection ──┐
│   └── model deployment                │
├── Log Analytics workspace ◄───────────┤ (ingestion target)
├── Application Insights ────────────────┘ (WorkspaceResourceId → LA workspace)
└── account-level connection (mirrors the project-level one)
```

## Repository artifacts

| Entity | Location | Format | Notes |
| --- | --- | --- | --- |
| Prompt | `genaiops/foundry-block3/prompts/*.prompty` | Prompty (YAML frontmatter + prompt body) | tracked in git; FR-006, SC-003 read its history directly, e.g. `git log --follow` |
| Call script | `genaiops/foundry-block3/call_model.py` | Python | loads a `.prompty` file, sends one completion request to the deployment, emits an OpenTelemetry span exported to the connected Application Insights (R6, R9) |
| Trace query script | `genaiops/foundry-block3/query_trace.py` | Python | queries the Log Analytics workspace for a specific past call's span, run as a separate invocation from `call_model.py` (FR-007, SC-004) |

### Call trace record (conceptual — lives in Application Insights, not a file)

| Field | Source | Used by |
| --- | --- | --- |
| Trace/span id | emitted by the OpenTelemetry SDK at call time | SC-004 — what `query_trace.py` looks up |
| Prompt version identifier | a span attribute set by `call_model.py`, e.g. the prompt file's git commit hash at call time | distinguishes two calls made with two different prompt versions (User Story 3, Acceptance Scenario 2) |
| Deployment identity | span attribute — the deployment name (`gpt-4.1-mini`) | confirms which deployment answered |
| Response content | span attribute or linked log entry | what SC-004 reads back |
| Timestamp | native to the span | ordering, not identity — two same-minute calls must still be distinguishable by prompt version, per Acceptance Scenario 2 |

No schema is defined beyond "the attributes above are present on every span
this feature emits" — Application Insights' schema is Microsoft's, not this
feature's to define.
