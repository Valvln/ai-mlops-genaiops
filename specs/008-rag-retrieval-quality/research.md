# Phase 0 research — Block 5

**Date**: 2026-08-27. **Branch**: `008-rag-retrieval-quality`.

This file is the *internal* decision record. Under constitution **1.1.0** it does
**not** satisfy the research requirement on its own — the six sourced notes in
`docs/exam-notes/` do, and they were written and committed before this plan
started (`8e83719`, `1fb0e59`, `59a48bb`).

What follows is different in kind from those notes. They record what the
documentation says. This records what was **checked against the live
subscription and the live packages today**, and the four places where the answer
was not what the spec assumed.

Every `az` command below was run against subscription
`5900fbc9-a139-49ed-9987-ba560c147eb7` on 2026-08-27, read-only.

---

## R1 — `Microsoft.Search` is not registered on this subscription

**Decision**: register the resource provider as the first pre-flight step, before
any template is built or deployed.

```bash
az provider show -n Microsoft.Search --query "{ns:namespace,state:registrationState}" -o json
# {"ns": "Microsoft.Search", "state": "NotRegistered"}
```

**Rationale**: an unregistered provider fails the deployment with
`MissingSubscriptionRegistration`, which reads like a permission problem and is
not one. Registration is free, asynchronous, and takes a few minutes. This
subscription has never created a search service, so nothing registered it.

**Alternative rejected**: discovering it from the first failed deployment. It
would be recorded as a finding rather than avoided, and the constitution's
Validation-Before-Commit principle is specifically about not shipping a template
whose first real exercise is the failure.

---

## R2 — `swedencentral` is the correct region, and `northeurope` is doubly wrong

**Decision**: `swedencentral`, for both the Foundry account (already established
in block 3) and the search service. FR-004's pre-creation check is hereby
**satisfied at plan time**, not deferred to implementation.

**Rationale**, from the region-support table read 2026-08-27:

| Region | Semantic ranker | Free-tier semantic ranker | New services creatable |
| --- | --- | --- | --- |
| **Sweden Central** | ✅ | ✅ (footnote 1) | ✅ |
| North Europe | ✅ | **✘** — no footnote 1 | **✘** — footnote 2 |

> ^1^ «This region supports agentic retrieval and semantic ranker **on the free
> tier**.»
> ^2^ «This region is in **high demand, which prevents the creation of new search
> services**. Please choose a different region.»

Two independent disqualifications for `northeurope`, which is this repository's
own documented default (`CLAUDE.md`: "Azure region: use `northeurope`"). The
default is right for the classical-ML infrastructure it was written for and
wrong here, and that is worth writing down rather than silently working around.

**This also refines a note.** `rag-hybrid-search-and-ranking.md` records that
semantic ranking runs on the Free tier because the free *billing plan* is
available on all tiers. True, and incomplete: it is available on all tiers **in
the regions that carry footnote 1**. The billing plan and the regional
capability are two separate gates, and the note names only the first. This is a
verification-with-correction under FR-024, not a contradiction.

**Alternative rejected**: splitting Foundry and Search across regions. Costs
nothing in money and buys nothing; both work in `swedencentral`.

---

## R3 — `text-embedding-3-large` has **zero** GlobalStandard quota in `swedencentral`

**Decision**: deploy `text-embedding-3-large` on the **regional `Standard`** SKU,
not `GlobalStandard`. Rate 0,0002 €/1K instead of 0,0001 €/1K.

```bash
az cognitiveservices usage list -l swedencentral \
  --query "[?contains(name.value,'embedding')].{name:name.value,limit:limit}" -o table
```

| Quota name | Limit |
| --- | ---: |
| `OpenAI.Standard.text-embedding-3-large` | **350** |
| `OpenAI.GlobalStandard.text-embedding-3-large` | **0** |
| `OpenAI.DataZoneStandard.text-embedding-3-large` | **0** |
| `OpenAI.GlobalStandard.text-embedding-3-small` | 1000 |

**Rationale**: `az cognitiveservices model list -l swedencentral` advertises
`text-embedding-3-large` with `skus: Standard, GlobalStandard, DataZoneStandard`
— the model *is offered* on all three. The quota for two of them is zero. **A
model being available and a model being deployable are different facts**, and
only the second one is a quota query. This is block 3's R4 lesson recurring in a
new place, and it would have failed the first deployment of an otherwise
correct template.

**Cost consequence**: the corpus costs ≈0,011 € to embed instead of ≈0,006 €.
Immaterial in money, decisive in whether the template deploys. The spec's Cost
table already quotes the 0,0002 €/1K regional rate, so no spec figure changes.

**Alternative rejected**: `text-embedding-3-small` on GlobalStandard, where
quota is 1000. Its retail price publishes as literal `0.0` in EUR — a rounding
artifact, not a free model (`rag-cost-model.md` § 3) — and building on a
published zero is a mistake this project has already made once.

**Chat model re-check, same command**: `OpenAI.GlobalStandard.gpt4.1-mini` limit
**200**, current 0. `foundry.bicep`'s `capacity: 10` fits. Note the meter's
spelling, `gpt4.1-mini` without the first hyphen — the trap already documented at
`infra/foundry.bicep:160`.

---

## R4 — The subscription is empty, and both soft-delete traps are clear

```bash
az group list --query "[].name" -o tsv                     # (nothing)
az cognitiveservices account list-deleted                  # []
az monitor log-analytics workspace list-deleted-workspaces # 2 rows, see below
```

**Zero resource groups. Zero soft-deleted Cognitive Services accounts** — block
3's `ai300fdrylkcq74thutjeq` is gone, its 48-hour window long expired. The spec's
Context section warned about it; it is no longer a constraint.

**Two soft-deleted Log Analytics workspaces remain**, both from long-dead test
groups:

| Workspace | Original resource group | Region |
| --- | --- | --- |
| `ai300law2mgou37pfmjou` | `rg-ai300-test01` | northeurope |
| `ai300lawmxvtm2okukvmy` | `rg-ai300-test02` | northeurope |

Neither belongs to `rg-ai300-foundry`, which means block 4's F8 fix — deleting
the workspace explicitly with `--force true` — was actually applied at that
block's teardown. The property was kept.

**Decision**: deploy into a **new resource group, `rg-ai300-rag`**, and keep the
F8 discipline at teardown. The new name changes
`uniqueString(resourceGroup().id)`, which changes every derived resource name,
which makes a silent restore impossible by construction rather than by
remembering. That is cheaper than trusting a check.

---

## R5 — Adding an embedding deployment reintroduces F1's race unless it is chained

**Decision**: the new `text-embedding-3-large` deployment is inserted **into**
`foundry.bicep`'s existing dependency chain, not declared alongside the chat
deployment.

The chain block 4 arrived at, after three failed attempts:

```text
account → chat deployment → project → account connection → project connection
```

becomes

```text
account → chat deployment → embedding deployment → project → account connection → project connection
```

**Rationale**, quoting F1 directly: «The pairs were never the point. *Every*
child of a Cognitive Services account contends for the same account-level lock.»
Two sibling `accounts/deployments` are exactly that shape. Declared without an
edge between them, ARM issues both concurrently and Azure rejects the loser with
`RequestConflict` — roughly half the time, which is the worst possible failure
rate because it passes often enough to look fixed.

**This is the highest-risk edit in the feature.** It touches the one property
block 4 paid four failed deployments to acquire, and `az bicep build` cannot see
it. Only FR-017's two consecutive deployments can.

**Alternative rejected**: a second Foundry account for the embedding model.
Doubles the surface, and the spec's constraint 6 excludes anything that grows the
resource footprint without a measurement behind it.

---

## R6 — `Foundry User` is granted by GUID; whether it is *sufficient* is the measurement

**Decision**: replace the `Cognitive Services OpenAI User` grant at
`infra/foundry.bicep:411-427` with **Foundry User**, by role-definition GUID
`53ca6127-db72-4b80-b1b0-d745d6d5456d`, at the account scope. Keep the name out
of the template, per Learn's own advice for scripts during the rename.

| Current name | Previous name | GUID |
| --- | --- | --- |
| **Foundry User** | Azure AI User | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |

**Rationale**: `docs/exam-notes/foundry-rbac-and-authentication.md` § 3 quotes
Learn prescribing exactly this — «To call a deployment at inference time, assign
the **Foundry User** role on the **Foundry account scope**» — and explicitly
advising against every role whose name begins with `Cognitive Services`. The
current grant works and is not what is prescribed. That divergence is the reason
constitution 1.1.0 exists.

**What is deliberately not decided here**: whether the call actually succeeds
under Foundry User alone. Learn's permission matrix says Foundry User carries
data actions; block 3's `401` was resolved by a different role and never re-tested
against this one. **The plan does not assume the outcome.** FR-016 records
success as a confirmation and failure as a finding, with the older grant restored
and the finding cited beside it. Either result is a deliverable; only an
unrecorded result is a failure.

---

## R7 — Free tier supports data-plane RBAC, and the default configuration silently refuses it

**Decision**: `infra/search.bicep` declares `disableLocalAuth: true` and **omits**
`authOptions` entirely, and grants the caller two roles at the service scope.

| Role | GUID | Why |
| --- | --- | --- |
| Search Service Contributor | `7ca78c08-252a-4471-8644-bb5ff32d4ba0` | create the index; read `/servicestats` |
| Search Index Data Contributor | `8ebe5a00-799e-43f5-93ac-243d3dce84a7` | push documents; query the index |

**Rationale**, three separate facts from the RBAC article read 2026-08-27:

1. **Tier is not a constraint.** «An Azure AI Search service (**any region and
   any tier**) with role-based access enabled.» The Free tier's restriction is on
   *outbound* managed identity for indexers, not on *inbound* Entra ID auth.
   Push-based ingestion is therefore fully credential-less on Free — the spec's
   assumption holds, and FR-003's downgrade clause stays dormant.
2. ⚠️ **The default is key auth, and RBAC requests are refused before permissions
   are consulted.** «The default configuration for a search service is key-based
   authentication. If you don't change this setting to Both or Role-based access
   control, **all requests that use role-based authentication are automatically
   denied, regardless of the underlying permissions**.» This is block 3's `401`
   with a different resource provider: a refusal that reads like a missing role
   and is a service setting.
3. ⚠️ **`authOptions` and `disableLocalAuth` are mutually exclusive.** From the
   ARM reference: «[`authOptions`] cannot be set if `disableLocalAuth` is set to
   true» and «[`disableLocalAuth`] cannot be set to true if `dataPlaneAuthOptions`
   are defined.» Setting both — the intuitive "RBAC only, and here is how" — is a
   template that will not deploy.

**One consequence worth stating in advance**: `Search Index Data Contributor`
alone **cannot** read `/servicestats`. The permission table gives "Access quotas
and service statistics" to Owner, Contributor and Search Service Contributor
only. SC-005's measurement depends on the first role in the table above, not the
second. A plan that granted only the data role would produce a `403` on the one
call User Story 2 exists to make.

**API version**: `Microsoft.Search/searchServices@2025-05-01`, the latest
non-preview. `sku.name: 'free'`, `replicaCount: 1`, `partitionCount: 1`,
`hostingMode: 'default'`, `semanticSearch: 'free'`.

---

## R8 — `DocumentRetrievalEvaluator`: available, deterministic, and its defaults are a trap

**Decision**: `azure-ai-evaluation >= 1.18.3, < 2` — the same major pin block 4
uses — with `DocumentRetrievalEvaluator` constructed with **explicit**
`ground_truth_label_min=0, ground_truth_label_max=3`.

**Availability was verified, not assumed.** The class does **not** appear in the
stable `azure.ai.evaluation` package reference on Learn, which lists
`RetrievalEvaluator` and not `DocumentRetrievalEvaluator`. It is nonetheless
exported at the released tag:

```bash
curl -s ".../azure-ai-evaluation_1.18.3/.../azure/ai/evaluation/__init__.py" | grep DocumentRetrieval
# from ._evaluators._document_retrieval import DocumentRetrievalEvaluator
```

A documentation omission, not a missing feature. Recorded because "it is not in
the reference" would otherwise look like a reason to abandon the approach.

⚠️ **The SDK defaults and the documentation example disagree.** From the source
at that tag:

```python
def __init__(self, *, ground_truth_label_min: int = 0, ground_truth_label_max: int = 4, ...)
```

while the Learn example passes `ground_truth_label_min: 1, ground_truth_label_max: 5`
and annotates the defaults as `# SDK default: 0` / `# SDK default: 4`. **This is
precisely what FR-009 was written for**, and it is not hypothetical: `fidelity`
computes its relevance weights from `range(min + 1, max + 1)`, so a label range
declared one point off silently reweights the metric instead of raising.

**Label schema decided here**: graded **0–3**, where `0` is *not relevant* and
`1–3` are increasing degrees of relevance. `min=0` makes `0` the excluded floor
in the fidelity computation, which is the intended reading.

⚠️ **A second correction to the spec's own language.** FR-010 requires a metric
set with «no judge model and **no pass threshold**». The first half is exactly
right — this evaluator is arithmetic over human labels and makes no model call.
The second half is not: the constructor carries seven thresholds
(`ndcg_threshold=0.5`, `xdcg_threshold=50.0`, `fidelity_threshold=0.5`,
`top1_relevance_threshold=50.0`, `top3_max_relevance_threshold=50.0`,
`total_retrieved_documents_threshold=50`,
`total_ground_truth_documents_threshold=50`) and emits `*_passed` labels against
them, with `ndcg@3` promoted to the top-level score.

**Resolution**: the *scores* are threshold-free and are what this feature
reports; the `*_passed` labels are advisory and are reported beside the scores
rather than in place of them. This is block 4's F5 in a new form — «an
LLM-as-judge metric has two independently wrong things, the score and the
threshold, and only the first is the model's» — except here neither is a model's.
The comparison is made on the numbers.

**Metrics emitted**: `ndcg@3`, `xdcg@3`, `fidelity`, `top1_relevance`,
`top3_max_relevance`, `total_retrieved_documents`,
`total_ground_truth_documents`, `holes`, `holes_ratio`.

FR-011 asks for a recall-shaped and a ranking-shaped metric: **`fidelity`** is
the recall-shaped one (good documents returned out of known good documents),
**`ndcg@3`** the ranking-shaped one. Learn's own worked example has them
disagreeing violently — `ndcg@3` 0.646 `pass` next to `fidelity` 0.019 `fail` —
which is the disagreement SC-004 asks to be shown.

---

## R9 — Labels are pooled across all four methods, and that fixes the sequencing

**Decision**: the labelled ground truth is built by **pooling** — running all four
retrieval methods first, taking the union of the documents they returned, and
labelling that union.

**Rationale**: `holes` counts retrieved documents carrying no relevance judgment,
and `holes_ratio` normalises it. Label a set chosen before retrieval and every
method surfaces documents nobody judged; the comparison then measures label
coverage rather than retrieval quality. Pooled judging is the standard practice
in information retrieval for exactly this reason, and here it is the mechanism
that makes SC-003 achievable rather than aspirational.

**Consequence for the plan's ordering** — and it is not the order the spec's
narrative implies:

```text
index → run all four methods → pool the union → label → score
```

Retrieval runs **before** labelling. The runs are re-usable: scoring consumes
stored run records, so a label correction re-scores without re-querying and
without re-embedding.

**Alternative rejected**: labelling from the corpus by hand, before retrieval. It
is how the spec reads at first glance, it doubles the labelling effort, and it
guarantees a high `holes_ratio` on the first pass.

---

## R10 — Package pins, verified against PyPI today

| Package | Pin | Latest on PyPI 2026-08-27 | Note |
| --- | --- | --- | --- |
| `azure-search-documents` | `>=12.0.0,<13` | **12.0.0** | `12.1.0b1` exists and is a beta; stable is taken |
| `azure-ai-evaluation` | `>=1.18.3,<2` | **1.18.3** | same major pin as block 4, patch raised to the version R8 verified |
| `azure-identity` | `>=1.19,<2` | — | reused from blocks 3 and 4 |
| `openai` | `>=1.60,<2` | — | reused; embeddings are called through it with an Entra token |
| `tiktoken` | `>=0.8,<1` | — | **local, free**: measures the corpus token distribution before chunking (FR-002) |

`uv`-managed, per the convention `genaiops/foundry-block3` and
`qa-observability/foundry-block4` both follow.

---

## R11 — The at-rest measurement needs a control, and this subscription has none

**Decision**: on the idle day, make **one deliberate token call** against the
Foundry chat deployment, and read Cost Management at **resource** granularity
rather than resource-group granularity.

**Rationale**: SC-010 requires that the search service's absent cost line be a
*measured zero* rather than an absent dataset, and asks for «at least one other
scope in the same subscription» producing a line that day. As of today the
subscription contains **nothing else** — zero resource groups. If the whole
subscription is silent, an empty result proves nothing, which is the exact
failure `foundry-cost-model.md` § 6 was written to prevent.

The Foundry deployment is per-token: one call costs a fraction of a cent and
produces a billing line. On that day the search service, in the same resource
group, produces none. Same window, same query, two resources, one line — the
comparison SC-010 actually wants.

**This does not change the criterion**, only the mechanism that satisfies it. The
control is a sibling resource rather than a sibling resource group, because a
sibling resource group would also be silent.

---

## R12 — `rag-optimization/` is this feature's folder, and it has been empty since day one

**Decision**: workload code goes in `rag-optimization/rag-block5/`.

The repository-structure table in the constitution reserves `rag-optimization/`
for "Retrieval-augmented generation work". It is the last of the four topic
folders to be occupied — `mlops/` (blocks 1–2), `genaiops/` (block 3),
`qa-observability/` (block 4). No new top-level folder is proposed.

---

## R13 — The CI approval gate will fire, and it must not be approved

**Not a decision, a warning carried into the plan.** `.github/workflows/infra-deploy.yml`
triggers on `push` to `main` with `paths: ['infra/**']`. This feature modifies
`infra/foundry.bicep` and adds `infra/search.bicep`, so merging it queues a
deployment of **`main.bicep`** — the classical-ML stack from blocks 1 and 2,
which does bill at rest — behind a human approval gate.

The gate is doing its job. Approving it would deploy infrastructure this feature
neither needs nor priced. **Leave it unapproved**, exactly as with the doc-only
triggers this repository has already accumulated.

The CI identity's role does not cover `Microsoft.Search` either, so even an
approved run would not deploy `search.bicep` — it deploys `main.bicep` only.
Adding the Search operations to `infra/ci-identity.bicep` is explicitly **not**
part of this feature (spec Assumptions).

---

## Two things this feature will document as case studies, at the author's direction

**The corpus is this repository's own notes.** That is a deliberate choice with
consequences that have to be stated rather than hidden: the corpus is small,
homogeneous in register, written by one person, and about the very technologies
being searched. Retrieval scores on it do not generalise to a heterogeneous
enterprise corpus, and the labeller is also the author, which is a bias no metric
here can detect. Written up as a case study — what it buys (accurate labels, zero
acquisition cost, full reproducibility from the repository) against what it costs
in external validity.

**Embedding happens locally, and pushes to the index.** The alternative — an
indexer with integrated vectorization — is the path Learn's tutorials take, and
it is unavailable here for two independent reasons: the Free tier grants no
managed identity for indexer outbound connections, and the tier's indexer runtime
cap is 1–3 minutes. Local embedding keeps the credential-less posture the rest of
this repository holds to. Written up the same way: the mechanism that was not
used is documented alongside the one that was, with the reason it was not
available.

---

## Sources

Live subscription reads, all 2026-08-27, subscription `5900fbc9-…147eb7`:
`az provider show`, `az group list`, `az cognitiveservices account list-deleted`,
`az cognitiveservices model list`, `az cognitiveservices usage list`,
`az monitor log-analytics workspace list-deleted-workspaces`.

- [Supported regions — Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-region-support) — read 2026-08-27; R2
- [Connect using Azure roles — Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac) — read 2026-08-27; R7
- [Microsoft.Search/searchServices — ARM/Bicep reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.search/searchservices) — read 2026-08-27; R7
- [RAG evaluators — Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators) — read 2026-08-27; R8, R9
- `azure-sdk-for-python`, tag `azure-ai-evaluation_1.18.3`, `_document_retrieval.py` — read 2026-08-27; R8
- PyPI JSON API for `azure-search-documents` and `azure-ai-evaluation` — read 2026-08-27; R10
- `specs/007-genai-eval-observability/findings.md` §§ F1, F5, F6, F8 — R4, R5, R8
- `docs/exam-notes/foundry-rbac-and-authentication.md` § 3 — R6
- `docs/exam-notes/rag-cost-model.md` §§ 3, 6 — R3, R11
- `docs/exam-notes/rag-hybrid-search-and-ranking.md` § 5 — R2's refinement
