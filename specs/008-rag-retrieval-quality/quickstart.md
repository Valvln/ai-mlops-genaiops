# Quickstart — validating Block 5 end to end

The runnable path from an empty subscription to a published comparison table and
back to an empty subscription. Roughly 8 days of calendar, of which one is the
idle day and one is spent labelling.

Every command is read-only or free unless the **Cost** column says otherwise.

```bash
export PATH="/usr/local/bin:$PATH"       # az and gh look uninstalled without this
```

---

## Prerequisites

| | |
| --- | --- |
| Subscription | Pay-As-You-Go, spending limit **Off**. Nothing caps spend |
| State | zero resource groups (verified 2026-08-27) |
| Region | `swedencentral` for everything |
| Local | `uv`, Python 3.11 |
| **Do not** | approve the CI deployment gate this branch will queue ([research.md § R13](./research.md)) |

---

## Day 1 — pre-flight and the two debts

```bash
# The one that will otherwise fail the first deployment
az provider register -n Microsoft.Search
az provider show -n Microsoft.Search --query registrationState -o tsv     # wait for Registered

az group list -o tsv                                                     # expect nothing
az cognitiveservices usage list -l swedencentral \
  --query "[?contains(name.value,'text-embedding-3-large')].{n:name.value,l:limit}" -o table
# Standard 350 / GlobalStandard 0  → the template says Standard
```

Then follow [contracts/foundry-redeployment.md](./contracts/foundry-redeployment.md):
edit the role grant, chain the embedding deployment, `az bicep build`, `what-if`,
**deploy twice consecutively**.

```bash
az group create -n rg-ai300-rag -l swedencentral
CALLER=$(az ad signed-in-user show --query id -o tsv)
az deployment group create -g rg-ai300-rag -n block5-001 -f infra/foundry.bicep -p callerPrincipalId=$CALLER
az deployment group create -g rg-ai300-rag -n block5-002 -f infra/foundry.bicep -p callerPrincipalId=$CALLER
cd genaiops/foundry-block3 && uv run call_model.py        # the SC-007 measurement
```

**Expected**: both deployments `Succeeded` (SC-008); the call either succeeds
under Foundry User alone (SC-007 confirmed) or fails and becomes a finding.
Either is a result. **Cost**: a fraction of a cent in tokens.

---

## Day 2 — the search service and the envelope

```bash
az bicep build -f infra/search.bicep
az deployment group create -g rg-ai300-rag -n block5-search-001 -f infra/search.bicep -p callerPrincipalId=$CALLER
az deployment group create -g rg-ai300-rag -n block5-search-002 -f infra/search.bicep -p callerPrincipalId=$CALLER

TOKEN=$(az account get-access-token --scope https://search.azure.com/.default --query accessToken -o tsv)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<service>.search.windows.net/servicestats?api-version=2026-04-01" | python3 -m json.tool
```

**Expected**: the Free tier's storage quota **and its vector index quota**, as
numbers. The second has no published value to check against — that is the point
(SC-005). **Cost**: 0,00 €.

---

## Day 2–3 — corpus, index, ingestion

```bash
cd rag-optimization/rag-block5
uv sync

uv run chunk_corpus.py --report          # tiktoken: token distribution FIRST (FR-002)
uv run create_index.py                   # data-plane, needs Search Service Contributor
uv run embed_and_push.py                 # ~55.000 tokens ≈ 0,011 €
uv run service_stats.py --index          # measured vector index size vs the formula (SC-006)
```

**Expected**: ≈145 chunks; measured vector index ≈1,8 MB against a 50 MB limit; a
`documentCount` matching the chunk count. **Cost**: ≈0,01 € once.

---

## Day 4 — the four runs

```bash
uv run run_retrieval.py --method keyword
uv run run_retrieval.py --method vector
uv run run_retrieval.py --method hybrid
uv run run_retrieval.py --method hybrid_semantic
```

One query embedding per question, reused across all four. **Expected**: four run
files, each row carrying its score **and** the property the score came from.
**Cost**: negligible (query embeddings only; semantic ranking is on the free
plan and stops with a billing error rather than a charge).

---

## Day 5 — labelling, the part no command replaces

```bash
uv run pool_for_labelling.py             # union of everything the four methods returned
# then label questions/labels.jsonl by hand, 0-3
```

⚠️ Labels are the ground truth. Where the author's prior and the label disagree,
**the label wins** and the correction is recorded. This is the only artifact here
that no command can regenerate, and the only one that must be committed.

---

## Day 6 — scoring and the table

```bash
uv run score_retrieval.py --all --out results/comparison.md
```

**Expected**: `ndcg@3` and `fidelity` per method, plus `holes_ratio`.

**Gate before publishing**: if `holes_ratio` is high, extend the pool and label
again. A comparison over unjudged documents is declared unreliable, not published
with a caveat (SC-003).

Read the table for the two things it has to say in words: whether the observed
ordering matches Learn's assertion and by **what margin** (SC-002), and at least
one case where the recall-shaped and ranking-shaped metrics disagree (SC-004).

---

## Day 7 — write-up

- `rag-optimization/rag-block5/README.md`, first person, the author's account.
- The **corpus as a case study** and the **local-embedding decision as a case
  study**: what each buys, what each costs, what neither proves.
- Each of the six research notes gains a **verification** or a **finding**
  (SC-012). Two are already owed at plan time: the regional gate on free-tier
  semantic ranking, and model availability ≠ quota for `text-embedding-3-large`.
- `specs/008-rag-retrieval-quality/findings.md`, block 4's format.

---

## Day 8 — the idle day, then teardown

**A full day with everything in place and no calls to the search service.**

⚠️ The subscription contains nothing else, so an empty cost result would be an
absent dataset, not a measured zero. Make **one** deliberate chat call that day
to produce the control line, and query at **resource** granularity
([research.md § R11](./research.md)):

```bash
az costmanagement query --type ActualCost --timeframe Custom \
  --time-period from=<idle-day> to=<idle-day> \
  --scope "/subscriptions/5900fbc9-a139-49ed-9987-ba560c147eb7"
```

**Expected**: a line for the Foundry account, **no line for the search service**
(SC-010). Cost Management lags; the query is run a day or two later, as blocks 2
and 3 both had to.

```bash
az cognitiveservices account deployment list -n <account> -g rg-ai300-rag -o table   # SC-011: no *-ft deployment
az group delete -n rg-ai300-rag --yes
az monitor log-analytics workspace list-deleted-workspaces -o table                  # F8: force-delete if present
az group exists -n rg-ai300-rag                                                      # false — SC-009
```

⚠️ Teardown is a **criterion**, not a closing note. And a free search service
being «deleted after extended periods of inactivity» is documented behaviour, not
a teardown mechanism.

---

## If time runs short

Cut in this order, and say so rather than leaving work open:

1. **US1's worked example in prose** — the table still stands without it.
2. **US3's role measurement** — the redeployment still happens; only the debt
   goes unsettled, and it is already a written debt.
3. **Never US2.** It is the cheapest story, it needs no labels, and it produces
   the number Learn does not publish.

Not on the list because it is already cut: the chunk-size sweep. Reinstating it
re-embeds the corpus once per cell.
