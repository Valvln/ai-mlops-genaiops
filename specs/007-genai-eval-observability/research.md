# Research: Block 4 — GenAI QA and Observability

Every decision below is checked against either a live, free, read-only Azure query
(matching the technique spec 006's research already established), this repository's own
recorded history (`specs/006-foundry-genaiops/tasks.md`, `infra/foundry.bicep`), or a
dated Microsoft Learn / package source, current as of this session (2026-08-23).

## R1 — The redeploy target is soft-delete-locked until 2026-08-24T00:17:31Z, and this is a known-shaped trap

**Decision**: Before `infra/foundry.bicep` is redeployed into `rg-ai300-foundry`, purge
the soft-deleted Foundry account explicitly with `az cognitiveservices account purge -g
rg-ai300-foundry -n ai300fdrylkcq74thutjeq -l swedencentral`, rather than waiting out the
hold or renaming the resource group.

**Rationale**: This is not a hypothetical edge case — it is already recorded, with exact
values, in `specs/006-foundry-genaiops/tasks.md` (T028's closing note). Feature 006's
teardown on 2026-08-22 deleted the resource group cleanly, but
`az cognitiveservices account list-deleted` still holds `ai300fdrylkcq74thutjeq`
(`swedencentral`), soft-deleted at `2026-08-22T00:17:31Z` with `scheduledPurgeDate`
`2026-08-24T00:17:31Z` — a **48-hour hold**, the same shape as the Key Vault trap
`infra/DEPLOY.md` already documents, but on a shorter clock and, unlike a vault with
purge protection on, endable early. The account name derives from
`uniqueString(resourceGroup().id)`, which is a pure function of the resource group's
resource id — so recreating `rg-ai300-foundry` under its existing name reproduces the
exact same account name and collides with the still-held soft-delete registry until the
hold expires or is purged. `az cognitiveservices account purge` is documented for exactly
this: ending the hold on demand, at no cost, with no effect beyond finalizing a deletion
already committed at T028.

**Alternatives considered**: Waiting until 2026-08-24T00:17:31Z passes on its own —
rejected as unnecessary friction; the hold exists to allow accidental-deletion recovery,
and this deletion was deliberate, measured, and already the closing act of feature 006.
Renaming the resource group to sidestep the collision — rejected because it changes
`uniqueString`'s input for no benefit, deviates from the template's already-verified
naming without a reason tied to this feature's scope, and leaves the old soft-deleted
registry to purge on its own timer regardless, so nothing is actually avoided.

**One instruction for implementation**: this purge is a mutating Azure call, not a
read-only check like the rest of this research — it must be run as an explicit,
author-authorized action at implementation time, not folded into a "just redeploy"
step. `az cognitiveservices account list-deleted` should be re-run immediately before it,
in case the exact soft-delete name or timestamp has drifted from what's recorded here.

**Confirmed at implementation time (2026-08-23)**: re-running the check found the account
still held, with the name and both timestamps exactly as recorded above — the hold had
roughly 22 hours left to run. Two things this check added that the desk research did not
predict:

- **The hold consumes quota.** `az cognitiveservices usage list -l swedencentral` reports
  `OpenAI.GlobalStandard.gpt4.1-mini` at `currentValue 1.0` against a limit of `200.0`,
  even though the resource group is gone and nothing is deployable. The soft-deleted
  account is still holding the capacity its deployment reserved. Irrelevant at a limit of
  200 and a usage of 1, and decisive on a meter with a limit of 1 — which several
  region/model pairs have. A quota check run against a subscription with a recent
  teardown reads low for a reason that has nothing to do with what is running.
- `az group exists --name rg-ai300-foundry` returns `false`, confirming that the
  resource-group-level view and the soft-delete registry genuinely disagree. This is the
  blind spot feature 006's own quickstart flagged at teardown; here it is from the other
  side, at the moment it would actually bite.

## R2 — Evaluation runs locally, against the SDK's evaluators, not through Foundry's cloud evaluation

**Decision**: Evaluation results are produced by calling `azure-ai-evaluation`'s
evaluator classes (`GroundednessEvaluator`, `RelevanceEvaluator`) directly from a local
script, the same posture `call_model.py` already takes toward the model deployment — not
by uploading a dataset to Foundry's server-side "cloud evaluation" feature and reading
results back from the portal.

**Rationale**: Microsoft's own documentation for local evaluation
([Local Evaluation with the Azure AI Evaluation SDK][eval-sdk]) draws the line plainly.
Calling an evaluator directly (`groundedness_eval(query=..., response=..., context=...)`)
or running `evaluate()` locally needs nothing beyond the package and a model
configuration. **Logging those results into the Foundry project's own portal UI** is
what pulls in the extra dependency: the same page's "Prerequisite set up steps" call for
connecting a storage account to the project — "Create and connect your storage account to
your Foundry project at the resource level" — and grant `Storage Blob Data Owner` on top
of it. Cloud evaluation (running the job server-side rather than locally) carries the
same requirement from the other direction, per
[Cloud evaluation prerequisites][cloud-eval]: a Foundry project, a GPT deployment, and
(optionally, but the storage layer is what backs the default) portal-visible results
storage.

This project already ruled out exactly this shape of dependency once, in block 3's own
build: the Foundry-project-native tracing connection was refused specifically because the
only role that grants the lookup needed is the entire Cognitive Services data plane, and
a narrower custom role would survive `az group delete` as residue (`infra/foundry.bicep`,
the "connections" comment block). A storage account tied to the project is the same shape
of avoidable dependency, in a different feature — it would add a resource this spec's
Cost section would then have to price and would have to justify as more than a
convenience, for a portal view this feature does not need: FR-004 and SC-002 only require
results to be *retrievable*, and this project's own trace store (Application Insights,
already deployed) already satisfies that.

**Alternatives considered**: `evaluate()` with `azure_ai_project` set, to get results in
the Foundry portal — rejected for the storage-account dependency above. `evaluate()`'s
batch/dataset path without `azure_ai_project` — viable and not excluded, but unneeded at
this feature's scale (a handful of test questions, not a dataset run); calling the
evaluator classes directly, one call at a time, is simpler and mirrors `call_model.py`'s
own one-call-at-a-time shape closely enough that the two scripts stay easy to reason
about together.

## R3 — Judge authentication is Entra ID, matching `disableLocalAuth: true` exactly

**Decision**: `AzureOpenAIModelConfiguration` is constructed with no `api_key`, letting
the SDK fall back to `DefaultAzureCredential` — the same credential object
`call_model.py` already uses.

**Rationale**: `infra/foundry.bicep`'s Foundry account sets `disableLocalAuth: true`
(spec 006's decision — "no API keys, anywhere in this feature"), so any evaluator that
required a key would be a hard blocker unless the account's auth policy were reopened,
which this feature has no standing reason to do. It doesn't need to: `azure-ai-evaluation`
1.12.0 added exactly this path — "Added support for user-supplied TokenCredentials with
LLM based evaluators" — and if `api_key` is omitted from `model_config`, "the prompty
runtime will automatically pick up `DefaultAzureCredential`", per the package's own
changelog. The account this feature redeploys already grants the calling identity
`Cognitive Services OpenAI User` (`infra/foundry.bicep`'s `callerInferenceGrant`) — the
exact role Microsoft's own evaluator setup docs name as sufficient ("make sure you have
at least the Cognitive Services OpenAI User role for the Azure OpenAI resource"). No new
role assignment, and no new Bicep, is needed for the AI-assisted evaluators this feature
uses.

**Alternatives considered**: Re-enabling local (key) auth on the account for evaluator
convenience — rejected outright; it would reopen a decision spec 006 made deliberately
and for a reason (no credential to store, rotate, or keep out of git) that has nothing to
do with this feature.

## R4 — `GroundednessProEvaluator` and the safety evaluators are out of scope, on purpose

**Decision**: This feature uses only evaluators that take a `model_config` (a GPT judge
deployment) — `GroundednessEvaluator`, `RelevanceEvaluator` — not
`GroundednessProEvaluator` or any of the `*Evaluator` risk/safety family
(`ViolenceEvaluator`, `ContentSafetyEvaluator`, etc.).

**Rationale**: Every evaluator in that second group takes `azure_ai_project` instead of
`model_config` — "instead of a GPT deployment in `model_config`, you must provide your
`azure_ai_project` information. This accesses the back end evaluation service by using
your Foundry project." That is the same connection-based access pattern block 3 already
refused for tracing discovery (R6 in that feature's own research), for the same reason:
the permission surface it needs is broader than this feature's actual objective, and this
feature's objective — a groundedness check the exam names explicitly — is already fully
served by `GroundednessEvaluator`'s `model_config` path.

**Alternatives considered**: `GroundednessProEvaluator`, described as more capable
because it's backed by Azure AI Content Safety's own service — rejected for the
`azure_ai_project` dependency, and because FR-005 asks for a groundedness check, not
specifically the "Pro" implementation of one.

## R5 — The judge is the same deployment as the one being evaluated, not a second one

**Decision**: `gpt-4.1-mini` (the deployment `infra/foundry.bicep` already creates) plays
both roles — it answers the calls under test, and it is the GPT judge configured in
`model_config` for the evaluators.

**Rationale**: Spec 006 already declined a second deployment on the same minimalism
argument this feature inherits: "a second deployment would double the SKU-eligibility and
cost bookkeeping for no exam objective this feature is scoped to cover." A separate judge
model is a genuine, well-known evaluation practice (reducing self-grading bias), but nothing
in this feature's spec asks for that rigor, and one deployment keeps FR-002/FR-003's
quota and SKU checks — and this feature's re-verification of them at implementation time,
per R1's own pattern — a single question instead of two. Microsoft's own docs list
`gpt-35-turbo`, `gpt-4`, `gpt-4-turbo`, `gpt-4o`, and `gpt-4o-mini` as the models they've
validated as judges; `gpt-4.1-mini` is not on that list, and this is flagged rather than
assumed clean.

**One instruction for implementation**: the first evaluator call against `gpt-4.1-mini`
is itself the check — if its `*_reason` field comes back well-formed and its numeric
score parses, `gpt-4.1-mini` works as a judge for this feature's purposes; if it doesn't,
the fallback is `gpt-4o-mini`, which does have real `Standard` quota in `swedencentral`
per feature 006's own research (R4 in that feature: quota confirmed, later rejected there
only for being deprecated as an *answering* model — its judge-model suitability was never
in question). Re-run `az cognitiveservices usage list -l swedencentral` for whichever
model is chosen, the same instruction R1 in feature 006's research already gave for this
exact reason: quota drifts between sessions.

## R6 — This feature's code lives in `qa-observability/`, not `genaiops/foundry-block3/`

**Decision**: A new folder, `qa-observability/foundry-block4/`, with its own
`pyproject.toml` (uv-managed, following the same convention `genaiops/foundry-block3` and
`mlops/training-pipeline` already use), holds this feature's scripts and prompt files.
`genaiops/foundry-block3/` is read from, not written to.

**Rationale**: The repository's own layout table draws this line already —
`qa-observability/` is reserved for "Quality assurance, monitoring, observability," a
distinct scope from `genaiops/`'s "Generative AI operationalization" — and this feature's
own framing (Block 4, AI-300 Domain 4, QA and observability) names exactly that scope.
The folder has stood empty since it was declared; this is its first use, the same
situation `genaiops/` was in when spec 006 became its first occupant. Constitution
Principle VII asks that new work go in the folder matching its topic, with a new
top-level folder proposed only when none fits — one already fits here, so none is
proposed.

**A consequence worth stating explicitly**: `qa-observability/foundry-block4/` shares a
span-name constant (`SPAN_NAME = "genaiops.call"`) with `genaiops/foundry-block3/`, read
but not owned by this feature. `call_model.py` and `query_trace.py` already duplicate
that constant deliberately rather than share an import, with the comment reasoning that a
mismatch is "the single most likely way this retrieval returns nothing while looking
healthy." The same reasoning applies across the folder boundary this feature adds: this
feature's scripts redeclare the constant locally (with the same comment) rather than
import across two independently `uv`-managed environments, keeping each topic folder
runnable on its own.

## R7 — The groundedness "fails on purpose" test is a hand-authored fixture, not a coaxed hallucination

**Decision**: FR-005's failing-verdict acceptance scenario (User Story 3, Scenario 2) is
satisfied by evaluating one hand-written response containing a claim not supported by its
stated context — passed directly to `GroundednessEvaluator` as a `query`/`context`/
`response` triple — not by prompting the live model until it happens to hallucinate.

**Rationale**: A live call cannot be relied on to produce an unsupported claim on demand;
treating "make the model say something wrong" as a test step would make this feature's
verification non-deterministic and would spend invocations (against SC-006's cap) on a
gamble. `GroundednessEvaluator` scores whatever `query`/`context`/`response` triple it is
given — nothing in its contract requires the response to have come from a live call in
the same run — so a fixture response, written once and committed alongside the passing
case, is a controlled, repeatable, zero-additional-model-call way to exercise the failing
branch. The passing case (Acceptance Scenario 1) still comes from a real call against the
redeployed deployment, so the feature still demonstrates a genuine grounded response, not
only a synthetic one.

**Alternatives considered**: Prompting the model adversarially until it hallucinates —
rejected for the non-determinism and invocation-budget reasons above. Using two live
calls with deliberately mismatched context (a real call whose context is swapped for an
unrelated document before evaluation) — a reasonable alternative that stays closer to
"real" data; not chosen only because the fixture is simpler and equally valid against
FR-005's actual requirement, which is about the evaluator's behavior, not the origin of
the text it scores.

## R8 — Two prompt revisions, evaluated, mirror block 3's own narrative

**Decision**: A new prompt file, `prompts/grounded-qa.prompty`, is authored in this
feature and iterated across at least two committed revisions — the first with a bare
instruction ("answer the question"), the second refined to constrain the model to the
supplied context ("answer only from the material given; say so if it isn't covered") —
and both revisions are evaluated with the same metric to demonstrate User Story 2's
comparison.

**Rationale**: This deliberately repeats the shape of block 3's own prompt-iteration
story (three revisions of `hello-domain3.prompty`, each correcting the last), applied to
a metric instead of to manual reading — which is exactly what Domain 4 adds on top of
Domain 3's versioning. It also gives SC-004's "which revision scored higher" a real,
expected direction to check against: a context-constrained instruction should reduce
ungrounded elaboration relative to a bare one, so the comparison has a predicted outcome
to confirm rather than an arbitrary one to describe after the fact.

**Alternatives considered**: Reusing `hello-domain3.prompty` itself for the comparison —
rejected because it has no `context` field and its existing three revisions already
closed out block 3's own success criteria; repurposing it here would blur which feature a
given revision belongs to. A new, dedicated prompt file keeps the two features'
git history independently readable (SC-005 asks for `git log --follow` on the file *used
for this feature's comparison*, which only holds cleanly if the file is this feature's
own).

## Cost re-derivation: the AI-assisted evaluator's own token ceiling, not a generic estimate

**Finding**: The spec's Cost section sized a 500-call worst case at 500 input + 200
output tokens/call (≈€0.045) as a placeholder pending this plan's specifics. The actual
per-call ceiling for an AI-assisted evaluator is higher and is worth restating precisely:
Microsoft's own evaluator docs note the judge prompt sets `max_token` to 800 for most
AI-assisted evaluators (the value quoted for `GroundednessEvaluator`/`RelevanceEvaluator`
specifically), and a judge prompt carrying the query, response, context, and grading
rubric plausibly runs 1,000–2,000 input tokens for this feature's short exam-style
material. Recomputed at `gpt-4.1-mini` `GlobalStandard` rates (input €0.351/1M, output
€1.406/1M, per `specs/006-foundry-genaiops/research.md` § R4) and SC-006's 500-invocation
ceiling: 500 × 2,000 input + 500 × 800 output ≈ 1.0M input + 0.4M output tokens ≈
**€0.351 + €0.562 ≈ €0.91** in the genuine worst case — still comfortably a rounding
error, and still an order of magnitude below the spec's own "generous budget" framing,
but a truer number than the placeholder it's replacing. This does not change SC-006 (the
invocation count is the binding cap, not a euro figure) or SC-008 (still €0.00 at rest);
it only sharpens what "well under the ceiling" means in practice — this feature's actual
verification, at a handful of calls plus a handful of evaluator calls, is expected to
land under 30 invocations total, not anywhere near 500.

## Package pin: `azure-ai-evaluation`

**Decision**: `azure-ai-evaluation>=1.18,<2`, Python 3.11 (matching `genaiops/foundry-block3`'s
pin), added to `qa-observability/foundry-block4/pyproject.toml`.

**Rationale**: Latest published release is `1.18.3` (PyPI, checked this session);
`requires_python` is `>=3.9`, so it is compatible with this repository's existing 3.11
pin without forcing a change. Pinned to a floor rather than an exact version, matching
`genaiops/foundry-block3`'s own `pyproject.toml` convention for its own dependencies
(constitution Principle II asks that versions be verified against current documentation,
not copied from memory — this is that verification, recorded rather than assumed).

---

## Sources

- `specs/006-foundry-genaiops/tasks.md`, T028 closing note — the soft-deleted account
  name, timestamps, and purge instruction (R1)
- `infra/foundry.bicep` — `disableLocalAuth`, `callerInferenceGrant`,
  the account/project/deployment this feature redeploys unchanged
- [Local Evaluation with the Azure AI Evaluation SDK][eval-sdk] — evaluator classes,
  `model_config` vs `azure_ai_project`, storage-account prerequisite for portal logging,
  `max_token` ceiling (R2, R4, cost re-derivation)
- [Cloud evaluation prerequisites][cloud-eval] — cloud evaluation's own resource list
  (R2)
- `azure-ai-evaluation` PyPI release history, this session — TokenCredential support
  added in 1.12.0, current version 1.18.3, `requires_python>=3.9` (R3, package pin)
- `az cognitiveservices account purge --help`, this session — exact command shape (R1)
- `specs/006-foundry-genaiops/research.md` § R4 — `gpt-4.1-mini` `GlobalStandard`
  pricing and quota-check method, reused here (R5, cost re-derivation)

[eval-sdk]: https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk
[cloud-eval]: https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/cloud-evaluation
