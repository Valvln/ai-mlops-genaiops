# Contract: redeploying `infra/foundry.bicep` from an empty resource group

What FR-001, FR-002, FR-003, SC-001, and this feature's Context section (the
redeployment-as-proof framing) require, in the order they must happen.

## Pre-flight, in order

1. **Confirm the current soft-delete state**, not the one recorded in research.md § R1 —
   `az cognitiveservices account list-deleted` (a free, read-only, subscription-wide
   query; no `-g` needed since the group won't exist yet). If the recorded account
   (`ai300fdrylkcq74thutjeq`, `swedencentral`) is still listed and
   `scheduledPurgeDate` has not passed:
   - **Purge it**: `az cognitiveservices account purge -g rg-ai300-foundry -n
     ai300fdrylkcq74thutjeq -l swedencentral`. This is a mutating call — run it as an
     explicit, author-authorized action, not silently as part of a larger script.
   - If the purge date has already passed, or the account no longer appears, no action
     is needed; the name is free.
2. **Recreate the resource group**: `az group create --name rg-ai300-foundry --location
   swedencentral` (same name, same region as feature 006 — deliberate, per research.md §
   R1: renaming would only defer the same check to a future feature).
3. **`az bicep build infra/foundry.bicep`** — expected to pass trivially, since the file
   is unchanged from feature 006's validated version. Run anyway; a build that fails on
   an unmodified file would itself be a finding (a provider or CLI change since
   2026-08-19), not something to assume away.
4. **`az deployment group what-if --resource-group rg-ai300-foundry --template-file
   infra/foundry.bicep`**, reviewed against the live subscription before anything real
   deploys (constitution Principle V). Expect four `Create` changes (account, project,
   deployment, plus the Log Analytics/App Insights pair and their connections) — compare
   the count against feature 006's own recorded deployment, not just against "no errors."
5. **Re-verify `gpt-4.1-mini` `GlobalStandard` quota** in `swedencentral`:
   `az cognitiveservices usage list -l swedencentral --query
   "[?name.value=='OpenAI.GlobalStandard.gpt4.1-mini']"` (note the meter's own spelling,
   without the hyphen before `4.1` — feature 006's research already found the
   hyphenated form matches batch meters instead and silently reports a healthy quota for
   the wrong SKU). If quota has dropped to zero or the model is no longer offered,
   re-run the model-selection process feature 006's R4 used, don't assume the 2026-08-19
   figure still holds.

## Deploy

6. **`az deployment group create --resource-group rg-ai300-foundry --template-file
   infra/foundry.bicep --parameters callerPrincipalId=<author's object id>`** — an
   explicit action the author takes in the session it happens (FR-011), not scheduled or
   automated.

## Post-deploy verification (SC-001, and the redeployment-as-proof claim)

7. **`az cognitiveservices account deployment show`** against the new deployment —
   confirm SKU reads back as `GlobalStandard`, not merely what was requested (SC-001,
   restated from spec 006 because it is being checked again against a freshly created
   resource, not assumed carried over).
8. **`az resource list -g rg-ai300-foundry`** — confirm exactly the same resource count
   and types feature 006's own T028 baseline recorded (four resources: account, project,
   Log Analytics workspace, Application Insights component), as the concrete form of
   "the template recreated what it describes." A different count is not a redeployment
   that merely looks successful — it is one that built something else.

## What this contract does NOT require

No new API version is introduced by this feature — `infra/foundry.bicep`'s resource
declarations are unchanged from feature 006's validated versions, so there is nothing new
for `az bicep build` to catch that feature 006's own validation didn't already cover. No
change to `infra/ci-identity.bicep` or the CI pipeline — this redeployment is manual, the
same posture spec 006 already established and this feature does not reopen.
