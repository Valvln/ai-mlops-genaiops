# Contract — settling the two `foundry.bicep` debts

Covers **User Story 3**, FR-015 to FR-018, SC-007 and SC-008. Runs **first** in
wall-clock time: it produces the model deployments the other two stories consume.

Everything here is manual, from the CLI. Not CI — see
[research.md § R13](../research.md).

```bash
export PATH="/usr/local/bin:$PATH"
```

---

## Pre-flight — before the template is touched

| # | Check | Command | Expected |
| --- | --- | --- | --- |
| 1 | Resource provider | `az provider show -n Microsoft.Search --query registrationState -o tsv` | `Registered`. Was **`NotRegistered`** on 2026-08-27 — register it now, it is asynchronous ([R1](../research.md)) |
| 2 | Subscription is empty | `az group list --query "[].name" -o tsv` | no output |
| 3 | No soft-deleted account in the way | `az cognitiveservices account list-deleted -o tsv` | no output |
| 4 | Chat quota | `az cognitiveservices usage list -l swedencentral --query "[?name.value=='OpenAI.GlobalStandard.gpt4.1-mini'].limit" -o tsv` | ≥ 10. Note the meter spells it `gpt4.1-mini` |
| 5 | Embedding quota | `az cognitiveservices usage list -l swedencentral --query "[?contains(name.value,'text-embedding-3-large')].{n:name.value,l:limit}" -o table` | `Standard` **350**, `GlobalStandard` **0** ([R3](../research.md)) |

**Check 5 is the one that decides a line of the template.** Deploying
`text-embedding-3-large` on `GlobalStandard` in this region fails on quota, and
the failure is not visible to `az bicep build`.

---

## Template changes

### Change 1 — the prescribed role, by GUID

Replace the grant at `infra/foundry.bicep:411-427`.

| | Before | After |
| --- | --- | --- |
| Role | Cognitive Services OpenAI User | **Foundry User** |
| GUID | `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd` | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |
| Scope | account | account (unchanged) |

Requirements: assigned **by GUID**, never by display name (Learn's own advice
during the rename); **no** role whose name begins with `Cognitive Services` is
left anywhere in the template (FR-015).

The comment block above the grant is rewritten, not deleted. It currently records
how the `401` was discovered and why the old role was chosen — that history stays,
with the new paragraph explaining that the role that *worked* was not the role
that is *prescribed*, and that this feature is where the two were reconciled.

### Change 2 — the embedding deployment, chained

Add one `Microsoft.CognitiveServices/accounts/deployments@2025-06-01`:

| Property | Value |
| --- | --- |
| name | `text-embedding-3-large` |
| `sku.name` | **`Standard`** — not `GlobalStandard`, see pre-flight 5 |
| `sku.capacity` | 10 |
| `model.name` | `text-embedding-3-large` |
| `model.version` | `1`, pinned |
| `versionUpgradeOption` | `NoAutoUpgrade` |

⚠️ **It must be inserted into the dependency chain, not declared alongside the
chat deployment.** Target order:

```text
account → gpt-4.1-mini → text-embedding-3-large → project → account connection → project connection
```

Every child of a Cognitive Services account contends for the same account-level
lock; two sibling deployments with no edge between them race, and Azure rejects
the loser with `RequestConflict` about half the time ([R5](../research.md), block
4 § F1). Half the time is worse than always, because it passes often enough to
look fixed.

---

## Validation, in order

| # | Step | Command | Gate |
| --- | --- | --- | --- |
| 1 | Compiles | `az bicep build -f infra/foundry.bicep` | no errors. Proves syntax **only** |
| 2 | Group | `az group create -n rg-ai300-rag -l swedencentral` | created |
| 3 | What-if | `az deployment group what-if -g rg-ai300-rag -f infra/foundry.bicep -p callerPrincipalId=$(az ad signed-in-user show --query id -o tsv)` | region and name-length problems surface here, and nowhere earlier |
| 4 | **Deploy #1** | `az deployment group create -g rg-ai300-rag -n block5-001 -f infra/foundry.bicep -p callerPrincipalId=...` | `Succeeded` |
| 5 | **Deploy #2, immediately** | same command, `-n block5-002`, **no manual step in between** | `Succeeded` — this is SC-008 |
| 6 | Both deployments per-token | `az cognitiveservices account deployment list -n <account> -g rg-ai300-rag --query "[].{n:name,sku:sku.name}" -o table` | `GlobalStandard` and `Standard`. **No** name containing `Provisioned` |
| 7 | Workspace is new, not restored | `az monitor log-analytics workspace show -g rg-ai300-rag -n <ws> --query createdDate -o tsv` | today's date. Block 4 § F8: a silent restore reports as a successful create |
| 8 | No Cognitive Services role anywhere | `az role assignment list --scope <account-id> --query "[].roleDefinitionName" -o tsv` | contains `Foundry User`; contains nothing starting with `Cognitive Services` |

If step 4 or 5 fails, capture `az deployment operation group list` and identify
the **specific resource** that failed before changing anything. That is how F1
was narrowed from "the deployment is flaky" to one resource and one lock.

---

## The measurement — FR-016, SC-007

One inference call, under Foundry User alone.

```bash
cd genaiops/foundry-block3 && uv run call_model.py     # reused unchanged
```

| Outcome | What it means | What is written |
| --- | --- | --- |
| **Succeeds** | source and measurement agree | `infra/foundry.bicep:411` becomes the only line in this repository that is both **measured and prescribed**. Recorded as a verification in `foundry-rbac-and-authentication.md` § 3, and `genaiops/foundry-block3/README.md` is corrected where it documents the old path |
| **Fails** | they diverge | a **finding**: the verbatim `401`, the role that was assigned, the data action the refusal names, and which of source and measurement is wrong on that evidence. The old grant is restored **with the finding cited beside it** — not silently |

**The plan does not assume which.** Learn's permission matrix gives Foundry User
data actions; block 3's `401` was cleared with a different role and this
combination has never been exercised. Either result is a deliverable.

---

## What this contract does not cover

- The search service. Separate template, separate contract — deliberately, so
  that "the second deployment still works" stays an unambiguous statement about
  `foundry.bicep`.
- Anything provisioned. No stage of this feature deploys a PTU SKU.
