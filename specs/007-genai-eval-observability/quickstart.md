# Quickstart: Block 4 — GenAI QA and Observability

Validation path for this feature, end to end. Prerequisites assume
[research.md](./research.md)'s decisions are already implemented in
`qa-observability/foundry-block4/`, and that `infra/foundry.bicep` itself is unchanged
from feature 006.

## Prerequisites

```bash
export PATH="/usr/local/bin:$PATH"
az account show --query "{name:name, id:id}" -o tsv   # confirms the right subscription
```

- `rg-ai300-foundry` does not currently exist (feature 006's teardown deleted it
  2026-08-22).
- The soft-deleted Foundry account from that teardown may still be held — checked and
  cleared in step 1 below, not assumed either way.

## 0. Pre-flight: clear the soft-delete hold before it collides with the redeploy

```bash
az cognitiveservices account list-deleted -o table
# If ai300fdrylkcq74thutjeq (swedencentral) is listed and scheduledPurgeDate
# has not passed (research.md § R1: held until 2026-08-24T00:17:31Z), purge it
# explicitly — a mutating call, run deliberately, not as a background step:
az cognitiveservices account purge -g rg-ai300-foundry -n ai300fdrylkcq74thutjeq \
  -l swedencentral
```

## 1. Redeploy `infra/foundry.bicep`, unchanged

See [contracts/foundry-redeployment.md](./contracts/foundry-redeployment.md) for the full
pre-flight (quota re-check included). Abbreviated:

```bash
az group create --name rg-ai300-foundry --location swedencentral \
  --tags project=ai300-prep environment=learning

CALLER_OID="$(az ad signed-in-user show --query id -o tsv)"

az bicep build --file infra/foundry.bicep   # exit 0 — file is unchanged from feature 006

az deployment group what-if \
  --resource-group rg-ai300-foundry \
  --template-file infra/foundry.bicep \
  --parameters callerPrincipalId="$CALLER_OID"
# Review: same shape feature 006 already validated — account, project,
# deployment, Log Analytics + App Insights pair, two connections, one role
# assignment. A different shape means the file drifted since 006; it hasn't.

az deployment group create \
  --resource-group rg-ai300-foundry \
  --template-file infra/foundry.bicep \
  --parameters callerPrincipalId="$CALLER_OID" \
  --name ai300-foundry-block4-001

az resource list -g rg-ai300-foundry --query "[].type" -o tsv | sort
# Expect the same four types feature 006 recorded — the redeployment-as-proof
# claim in spec.md's Context is checked here, not asserted.
```

## 2. Set up the evaluation harness

```bash
cd qa-observability/foundry-block4
uv sync

ACCOUNT="$(az resource list -g rg-ai300-foundry \
  --resource-type Microsoft.CognitiveServices/accounts --query "[0].name" -o tsv)"
export AZURE_AI_FOUNDRY_ENDPOINT="https://${ACCOUNT}.cognitiveservices.azure.com/"
export APPLICATIONINSIGHTS_CONNECTION_STRING="$(az monitor app-insights component show \
  -g rg-ai300-foundry -a "$(az resource list -g rg-ai300-foundry \
  --resource-type Microsoft.Insights/components --query '[0].name' -o tsv)" \
  --query connectionString -o tsv)"
export LOG_ANALYTICS_WORKSPACE_ID="$(az monitor log-analytics workspace show \
  -g rg-ai300-foundry -n "$(az resource list -g rg-ai300-foundry \
  --resource-type Microsoft.OperationalInsights/workspaces --query '[0].name' -o tsv)" \
  --query customerId -o tsv)"
```

## 3. User Story 1 — score one call, retrieve the score separately

```bash
# The call (reuses block 3's own script, unchanged):
(cd ../../genaiops/foundry-block3 && uv run call_model.py prompts/hello-domain3.prompty)
# Note the printed trace id.

uv run evaluate_call.py --trace-id <trace-id> --metric relevance
```

Close this terminal, or at least don't rely on scrollback:

```bash
cd qa-observability/foundry-block4
uv run query_evaluations.py --trace-id <trace-id>
# Expect: the call's prompt version and deployment (from the joined
# genaiops.call record) alongside the relevance score, threshold, and
# pass/fail result. (SC-002)

# Confirm absence isn't mistaken for a zero (FR-008): pick a trace id that
# was never scored and query it.
uv run query_evaluations.py --trace-id <some-other-unscored-trace-id>
# Expect: "no evaluation found" in words, not a row with score 0.
```

## 4. User Story 3 — groundedness, both directions

```bash
# Grounded case — a real call:
(cd ../../genaiops/foundry-block3 && uv run call_model.py prompts/hello-domain3.prompty)
uv run evaluate_call.py --trace-id <that trace-id> --metric groundedness
uv run query_evaluations.py --trace-id <that trace-id>
# Expect eval.result = pass. (SC-003, pass case)

# Ungrounded case — the committed fixture, no live call, no extra invocation
# spent on the model being evaluated:
uv run evaluate_call.py --fixture fixtures/unsupported_claim.json --metric groundedness
uv run query_evaluations.py --trace-id fixture
# Expect eval.result = fail. (SC-003, fail case)
```

## 5. User Story 2 — two prompt revisions, compared

```bash
git log --follow --oneline -- prompts/grounded-qa.prompty
# Expect ≥2 commits (SC-005).

# Run both revisions (check out or reference each commit's content when
# calling), score each with the same metric, then:
uv run query_evaluations.py --compare <version-a> <version-b> --metric groundedness
# Expect a stated direction — which revision scored higher — not two bare
# numbers. (SC-004)
```

## 6. Count invocations against SC-006's cap

```bash
uv run query_evaluations.py --count-invocations --since 1d
# Sums genaiops.call + genaiops.eval spans in the window directly from the
# trace store, per contracts/evaluate-and-retrieve.md's accounting rule —
# never a total kept by hand outside the system. Expect well under 30 for
# this quickstart's own run, far inside the 500 ceiling.
```

## 7. Cost check (deferred — see spec's Deferred Criteria)

Same method spec 006's quickstart already established — not readable the day of
deployment (Cost Management lags 8–24h), and an absent row is "no data yet," never a
confirmed zero, unless read against a control resource group known to be billing the same
day (`infra/DEPLOY.md` § 4).

## 8. Teardown

```bash
az group delete --name rg-ai300-foundry --yes
az resource list -g rg-ai300-foundry   # expect empty / not found (SC-007)

# Same blind spot spec 006's quickstart already documented: az resource list
# cannot see a soft-deleted registry. Check it explicitly, and note the date —
# it becomes the next feature's own R1 if anything in this folder is rebuilt
# under the same resource group name within 48 hours.
az cognitiveservices account list-deleted -o table
az role definition list --custom-role-only true -o table
```
