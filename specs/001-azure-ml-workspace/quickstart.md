# Quickstart: Validating the Azure ML Workspace change

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**:
2026-08-06

Everything here runs locally and for free. **No command in this guide deploys
anything to Azure**, and none of them needs an active subscription — only `az
bicep build`, which works offline.

## Prerequisites

```bash
export PATH="/usr/local/bin:$PATH"   # az and jq are not on the default PATH in this environment
az bicep version                     # expect 0.46.1 or newer
jq --version
```

Run everything from the repository root.

## Build

```bash
az bicep build --file infra/main.bicep
```

**Expected**: exit code 0 and **no output at all**. Bicep prints nothing on a
clean build, so any line of output is a finding. In particular a `BCP081`
warning would mean an API version was used that the CLI cannot type-check — see
[research.md](./research.md) R3 for why that matters and why `2025-07-01` was
chosen for Log Analytics.

The build writes `infra/main.json`. That file is gitignored and must never be
committed.

## Assertions

Each block maps to one success criterion from the spec.

### SC-002 — exactly 5 resources

```bash
jq '.resources | length' infra/main.json
jq -r '.resources[].type' infra/main.json
```

**Expected**: `5`, and these five types in this order:

```text
Microsoft.Storage/storageAccounts
Microsoft.KeyVault/vaults
Microsoft.OperationalInsights/workspaces
Microsoft.Insights/components
Microsoft.MachineLearningServices/workspaces
```

### SC-003 — no container registry

```bash
grep -c containerRegistry infra/main.json || echo "0 matches — as expected"
```

**Expected**: no match. `grep -c` exits non-zero when it finds nothing, which is
the passing case here — hence the `|| echo`.

### SC-004 — no hardcoded subscription or tenant values

```bash
grep -nE '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' infra/main.json \
  | grep -v '"templateHash"' || echo "no GUIDs — as expected"
```

**Expected**: no match. The `templateHash` exclusion is there because ARM stamps
a build hash into every compiled template; it is not a subscription or tenant
identifier.

Additionally, the tenant id must still be resolved at deployment time rather
than baked in:

```bash
jq -r '.resources[] | select(.type=="Microsoft.KeyVault/vaults") | .properties.tenantId' infra/main.json
```

**Expected**: `[subscription().tenantId]` — an ARM expression, not a literal
GUID.

### SC-005 — outputs present

```bash
jq -r '.outputs | keys[]' infra/main.json
```

**Expected**: `keyVaultUri`, `storageAccountName`, `workspaceId`,
`workspaceName` (jq sorts keys).

### FR-005 — system-assigned managed identity

```bash
jq -r '.resources[] | select(.type|endswith("MachineLearningServices/workspaces")) | .identity.type' infra/main.json
```

**Expected**: `SystemAssigned`.

### FR-006 — Basic SKU

```bash
jq -r '.resources[] | select(.type|endswith("MachineLearningServices/workspaces")) | .sku' infra/main.json
```

**Expected**: `{"name": "Basic", "tier": "Basic"}`.

### D1 — Application Insights is workspace-backed

```bash
jq -r '.resources[] | select(.type=="Microsoft.Insights/components") | .properties.WorkspaceResourceId' infra/main.json
```

**Expected**: an ARM `resourceId(...)` expression referencing the Log Analytics
workspace, not empty and not a literal id. This is the check that would have
caught the retired-classic-component problem.

## One-shot script

```bash
az bicep build --file infra/main.bicep \
  && echo "build: OK" \
  && echo "resources: $(jq '.resources|length' infra/main.json) (expected 5)" \
  && echo "outputs:   $(jq -r '.outputs|keys|join(", ")' infra/main.json)" \
  && { grep -q containerRegistry infra/main.json \
       && echo "containerRegistry: FOUND — FAIL" \
       || echo "containerRegistry: absent — OK"; }
```

## What this does *not* prove

A clean build means the template **compiles** and is type-correct. It does not
mean it **deploys**. Name collisions, policy denials, quota limits, regional
availability, and the workspace's own deploy-time validation are all invisible
here. Per constitution principle V, report this change as *validated to
compile*, never as *verified to work*.

## Deployment (explicitly out of scope)

The spec forbids running `az deployment group create` as part of this feature,
and this guide contains no such command. When deployment is eventually
authorized as its own task, the cost-discipline principle applies: check what
the workspace provisions on creation before running it, and tear it down
afterwards.
