# Quickstart: Block 3 — Azure AI Foundry GenAIOps backbone

Validation path for this feature, end to end. Prerequisites assume
[research.md](./research.md)'s decisions are already implemented in
`infra/foundry.bicep` and `genaiops/foundry-block3/`.

## Prerequisites

```bash
export PATH="/usr/local/bin:$PATH"
az account show --query "{name:name, id:id}" -o tsv   # confirms the right subscription
```

- `Microsoft.CognitiveServices` provider `Registered` (done this session — R2;
  re-check with `az provider show --namespace Microsoft.CognitiveServices
  --query registrationState -o tsv` if this runs in a new subscription context).
- `rg-ai300-foundry` does not yet exist, or exists empty.

## 1. Pre-flight (free, read-only — run before touching the subscription)

```bash
az cognitiveservices model list -l swedencentral \
  --query "[?model.name=='gpt-4.1-mini'].{version:model.version, skus:join(',',model.skus[].name)}" -o table

# Note the spelling: gpt4.1-mini, NOT gpt-4.1-mini. The standard-SKU quota
# meters drop the hyphen after "gpt" while the batch meters keep it, so
# filtering on the model's real name matches the GlobalBatch/DataZoneBatch
# rows ONLY — and those report a healthy 50000 limit for a SKU nobody is
# deploying. Verified 2026-08-19 during T002.
az cognitiveservices usage list -l swedencentral \
  --query "[?contains(name.value,'gpt4.1-mini')].{name:name.value, limit:limit}" -o table
```

Expect `GlobalStandard` in the SKU list and a nonzero limit
(`OpenAI.GlobalStandard.gpt4.1-mini`, observed limit 200 on 2026-08-19). If
either has changed since [research.md](./research.md) § R4 was written, stop
and re-run the model/quota selection in R4 before continuing — do not deploy
against a stale assumption.

## 2. Create the resource group and deploy

```bash
az group create --name rg-ai300-foundry --location swedencentral \
  --tags project=ai300-prep environment=learning

az bicep build --file infra/foundry.bicep   # exit 0, no output

az deployment group what-if \
  --resource-group rg-ai300-foundry \
  --template-file infra/foundry.bicep
# Review: 7 creates, no PTU SKU, no hub, no AI Search. See
# contracts/foundry-deployment.md for the exact list.

az deployment group create \
  --resource-group rg-ai300-foundry \
  --template-file infra/foundry.bicep \
  --name ai300-foundry-block3-001
```

## 3. Verify the deployment matches the contract

```bash
az resource list -g rg-ai300-foundry --query "[].{name:name, type:type}" -o table
# Expect exactly the resources in data-model.md's Infrastructure entities table.

az cognitiveservices account deployment show \
  --name <foundry account name> -g rg-ai300-foundry \
  --deployment-name gpt-4.1-mini --query "sku.name" -o tsv
# Expect: GlobalStandard   (SC-001)
```

## 4. Make a call, using a versioned prompt

```bash
cd genaiops/foundry-block3
uv run call_model.py prompts/hello-domain3.prompty
# Prints a response and a trace id. Note the trace id; it is not needed by
# step 5's script, only by a human confirming step 5 found the right one.
```

```bash
git log --follow --oneline -- prompts/hello-domain3.prompty
# Expect ≥1 commit on first run; ≥2 after the prompt is edited once (SC-003).
```

## 5. Retrieve the trace — from a separate invocation, proving retrieval rather than assuming it

```bash
# Close this terminal, or at least don't rely on anything call_model.py
# printed above still being in scrollback.
cd genaiops/foundry-block3
uv run query_trace.py --since 10m
# Expect: prompt version (a git commit hash), deployment name (gpt-4.1-mini),
# and the response content, read back from Application Insights — not from
# memory. (SC-004)
```

## 6. Cost check (deferred — see spec's Deferred Criteria)

Not readable on the day of deployment (Cost Management lags 8–24h). The day
after:

```bash
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/query?api-version=2023-03-01" \
  --headers "Content-Type=application/json" \
  --body '{"type":"ActualCost","timeframe":"Custom","timePeriod":{"from":"<from>T00:00:00Z","to":"<to>T23:59:59Z"},"dataset":{"granularity":"Daily","aggregation":{"total":{"name":"Cost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceGroupName"}]}}'
```

A row for `rg-ai300-foundry` on a day with no calls sent should show a cost
matching only the (free-tier) Application Insights ingestion from the calls
already made — not a standing charge. An absent row means no data yet, not a
confirmed zero (`infra/DEPLOY.md` § 4's caution, restated in this spec's Edge
Cases).

## 7. Teardown

```bash
az group delete --name rg-ai300-foundry --yes
az resource list -g rg-ai300-foundry   # expect empty / not found (SC-007)
```
