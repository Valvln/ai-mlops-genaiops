# Research: Block 3 — Azure AI Foundry GenAIOps backbone

Every decision below was checked against the live subscription this session,
free and read-only (`what-if`, `usage list`, the public Retail Prices API), or
against a dated Microsoft Learn source. None is carried forward from the spec's
2026-08-18 snapshot without being re-verified — the spec itself requires that
(FR-004).

## R1 — Region: `swedencentral` is eligible for this subscription

**Decision**: Deploy in `swedencentral`.

**Rationale**: A `what-if` against a minimal `Microsoft.CognitiveServices/accounts`
probe (kind `AIServices`) in `swedencentral` returned `status: Succeeded`,
`changeType: Create`, with no `RequestDisallowedByAzure` — the failure this
subscription hits in `westeurope`. This is the same free technique
`infra/DEPLOY.md` § 0.2 uses for region sweeps, applied to a resource type
`main.bicep` doesn't declare.

**Alternatives considered**: `northeurope` — rejected before this feature was
scoped: every chat model in that region is `GlobalProvisionedManaged`-only
(PTU), which constraint 2 rules out categorically.

## R2 — The `Microsoft.CognitiveServices` provider needed registering

**Decision**: Registered this session (`az provider register --namespace
Microsoft.CognitiveServices`); confirmed `Registered` after ~30s.

**Rationale**: It was `NotRegistered` on this subscription — the same
pre-flight step `infra/DEPLOY.md` § 0.1 already documents for five other
providers, just never triggered before because nothing in `main.bicep` uses
this namespace. Free, harmless, and — per that section's own finding —
effectively permanent for the subscription. Registration is a prerequisite the
implementation task list should not have to rediscover.

**Evidence**: `az provider show --namespace Microsoft.CognitiveServices
--query registrationState` → `Registered`.

## R3 — API version and resource shape: validated end-to-end by `what-if`, not assumed

**Decision**: `api-version 2025-06-01` for `Microsoft.CognitiveServices/accounts`,
`accounts/projects`, and `accounts/deployments`.

**Rationale**: A three-resource probe (account, project, deployment nested as
Bicep child resources) built clean (`az bicep build`, exit 0) and what-if'd
clean (`status: Succeeded`, three `Create` changes, zero `ERROR:` lines) against
`rg-ai300-test02`. This is stronger evidence than the provider's
"apiVersions[:5]" listing, which didn't even include `2025-06-01` among its five
most recent entries — a reminder that "most recent" and "what the template
should pin" are different questions, and that the check is running the
template, not reading a version list.

**Not yet validated by `what-if`**: `Microsoft.CognitiveServices/accounts/connections`
and `accounts/projects/connections` (needed for R6, tracing). A public example
in the `microsoft-foundry/foundry-samples` GitHub repository uses
`2025-04-01-preview` for these — cited in R6, but **not yet run against this
subscription**. Re-verify with `az bicep build` and `what-if` before this part
of the template is proposed for deployment; do not carry the sample's version
forward on trust alone (constitution Principle II).

## R4 — Model: `gpt-5-nano` is blocked by quota, not by capability

**Decision**: Deploy `gpt-4.1-mini` (version `2025-04-14`), `GlobalStandard`
SKU, capacity 1.

**Rationale**: This is the finding that overturns the cost model's own
recommendation, and it's worth stating plainly: **`gpt-5-nano` is deployable in
`swedencentral` per the model catalog, but this subscription's quota for
`OpenAI.GlobalStandard.gpt-5-nano` is `0`**, confirmed two ways —

1. `az cognitiveservices usage list -l swedencentral` shows
   `OpenAI.GlobalStandard.gpt-5-nano`: current `0.0`, limit `0.0`.
2. Actually trying it: a `what-if` deploying `gpt-5-nano` at `GlobalStandard`
   failed preflight validation with `InsufficientQuota — This operation
   require 1 new capacity in quota ... which is bigger than the current
   available capacity 0`.

A model catalog listing a SKU as available (`az cognitiveservices model list`,
which the cost model and the spec's Context both relied on) says the SKU
*exists*; it says nothing about whether *this subscription* holds quota to use
it. That gap is exactly the kind of "check that passes while proving nothing"
this repository has hit before, just one layer earlier than usual — the model
list didn't fail, it just didn't answer the question the deployment needed
answered. Requesting a quota increase is a support-ticket process, not a
same-session, zero-cost action, so it's out of scope for "smallest deployment
this session."

The same probe-and-read method eliminated two more candidates before landing on
`gpt-4.1-mini`:

- `gpt-4o-mini` (`2024-07-18`, `Standard`) has real quota (`limit: 200`,
  `OpenAI.Standard.gpt-4o-mini`) but a `what-if` failed with
  `ServiceModelDeprecated — deprecated since 03/31/2026`. Cost-model snapshots
  age; model deprecation is exactly what makes them do so.
- `gpt-4.1-nano` and `gpt-4.1-mini` both show real `Standard`/`GlobalStandard`
  quota (limit `200` each) in `az cognitiveservices usage list`.
  `gpt-4.1-mini` at `GlobalStandard` **what-if'd clean** — no quota error, no
  deprecation error, alongside the account and project in the same probe (R3).

**Price** (swedencentral, `GlobalStandard`, Retail Prices API, `EUR`,
normalised to €/1M tokens): input **0.351**, output **1.406**. (`Standard`
SKU, same model: input 0.425, output 1.701 — kept as a fallback in case
`GlobalStandard` quota changes before implementation.) At this project's test
volume — a handful of short calls, not the cost model's 10M/2M budget sizing —
the realistic spend is a fraction of a cent; the €1.14 figure the spec quotes
from the cost model is a budget ceiling, not an estimate of what this feature
actually needs to spend.

**Alternatives considered and rejected with quota evidence**: `gpt-5-nano`
(R4, quota 0), `gpt-5-mini` (`GlobalStandard` quota 500 — viable, but pricier:
input 0.220 / output 1.757 €/1M, and no `Standard` fallback since it has none),
`gpt-4o` (`Standard` quota 50 — viable but more expensive per token than
`gpt-4.1-mini` and no `GlobalStandard` quota), `gpt-4o-mini` (deprecated).

**One instruction for implementation**: FR-004 already requires re-running
`az cognitiveservices model list -l swedencentral` at implementation time. Add
to that: re-run `az cognitiveservices usage list -l swedencentral` for the
chosen model too. A model can stop being deprecated-but-listed and start being
quota-zero (or vice versa) between now and then, and only the second command
would catch a quota change.

## R5 — Resource group: new and dedicated, not shared with `main.bicep`

**Decision**: A new resource group, `rg-ai300-foundry`, created in
`swedencentral`.

**Rationale**: Matches the spec's Assumption (FR-008 — independent
teardown). No resource in this feature shares a lifecycle with the
classical-ML backbone; keeping them in separate resource groups makes "destroy
this feature" a single `az group delete` that cannot touch the other block, the
same property `infra/main.bicep`'s own resource group already has for itself.

**Alternatives considered**: Reusing `rg-ai300-test02`. Rejected — it mixes
two features' teardown schedules (NEXT.local.md's "destroy before the
2026-09-03 absence" applies to the classical-ML environment on a timeline this
feature doesn't share) and its own location (`northeurope`) would be cosmetic
metadata sitting on top of `swedencentral` resources, worth avoiding for
clarity alone.

## R6 — Tracing: Application Insights connected to the Foundry project, via OpenTelemetry

**Decision**: One `Microsoft.Insights/components` (workspace-based, so also one
`Microsoft.OperationalInsights/workspaces`) plus a `connections` resource on
both the Foundry account and the Foundry project (category `AppInsights`),
sourced from the official `microsoft-foundry/foundry-samples` repository
([`connection-application-insights.bicep`][sample]). Call-side, the harness
uses OpenTelemetry (`opentelemetry-sdk`, `azure-core-tracing-opentelemetry`)
so each inference call emits a span exported to the connected Application
Insights resource.

**Rationale**, sourced from Microsoft Learn
([Observability in Microsoft Foundry][obs], [Set up tracing][trace]), current
as of 2026-07-31/2026-08-06:

- Foundry's tracing is "built on OpenTelemetry standards and integrated with
  Azure Monitor Application Insights" — there is no Foundry-native trace store
  independent of Application Insights.
- The connection is what makes a call retrievable **after the fact, from a
  separate session** (SC-004's exact requirement): traces land in Application
  Insights / the linked Log Analytics workspace, queryable by KQL at any later
  time, not only visible while a terminal is open.
- Querying requires the **Log Analytics Reader** role (and **Privileged
  Monitoring Data Reader** if the tables are protected) on the connected
  Application Insights resource — the sample assigns these to the project's
  system-assigned identity; the querying principal (the author, running
  `query_trace.py` locally) needs the same role.
- **Cost**: "Data retention and billing follow your Application Insights and
  Log Analytics configuration" — i.e., no separate tracing charge, just
  standard ingestion billing (per GB, with a free monthly allowance), the same
  meter `infra/main.bicep`'s own Application Insights already uses and stays
  "well inside" (`infra/DEPLOY.md` § 4). This feature's call volume is smaller
  still.

**Alternatives considered**: Foundry's built-in "server-side" agent tracing —
rejected as the primary mechanism because it's documented specifically for
Prompt/Host agents and workflows (Foundry Agent Service), not for a raw model
deployment call, which is this feature's actual scope (spec: "no embeddings
model... a second deployment would double the SKU-eligibility and cost
bookkeeping" — the same minimalism applies to not standing up Agent Service
for a single completion call). Client-side OpenTelemetry instrumentation is the
documented mechanism for exactly this case and is what's chosen.

**Not yet validated by `what-if`** (see R3): the `connections` resource shape
and API version. This is deferred to implementation, validated the same way R1
and R4 were validated here — by running it against the live subscription, not
by trusting the sample.

## R7 — Prompt format: `.prompty`, not Prompt Flow

**Decision**: The versioned prompt (FR-006) is a `.prompty` file — YAML
frontmatter (model config, inputs) plus a markdown-style prompt body — read
locally by the harness script, not authored or orchestrated through Foundry's
Prompt Flow.

**Rationale**: Prompty is a standalone, portable file format with its own
runtime library, independent of Prompt Flow. Prompt Flow itself is scheduled
for retirement (2027-04-20) and is "no longer recommended for new development"
— confirmed by web search this session — so building this feature's prompt
versioning on it would mean practicing a Domain 3 objective on infrastructure
already on its way out. A `.prompty` file versioned in git and loaded directly
by a small Python script satisfies FR-006 and SC-003 (git history on the file)
without depending on Prompt Flow at all, and Microsoft's own current training
material for prompt versioning teaches git-based prompt management as the
pattern to use.

**Alternatives considered**: Prompt Flow-orchestrated prompts (rejected —
retiring); a plain `.txt`/`.md` prompt string (rejected only because
`.prompty`'s frontmatter is free, gives a structured place to record the model
config alongside the prompt text, and is the format AI-300 material names —
the exam-relevance tiebreaker this repository's constitution treats as part of
the deliverable).

## R8 — Deployment mechanism: manual, not through the existing CI pipeline

**Decision**: The author runs `az deployment group create` directly against
`rg-ai300-foundry`. `infra/ci-identity.bicep` and the GitHub Actions pipeline
are not touched by this feature.

**Rationale**: Already the spec's Assumption; restated here because the CI
role's scope (`infra/DEPLOY.md` § 5) is a hard boundary, not a preference —
extending it to a second resource group is a bigger, harder-to-reverse change
than this feature's own footprint justifies. FR-012 stays in the spec in case
this is revisited, but nothing in this plan exercises it.

## R9 — Local harness: Python, `uv`-managed, mirrors `mlops/training-pipeline`

**Decision**: Python 3.11, dependencies pinned in a `pyproject.toml` managed
with `uv`, following the same local-baseline pattern feature 005 established
(`mlops/training-pipeline/pyproject.toml`).

**Rationale**: Consistency with the one other workload folder this repository
has built, and no reason to introduce a second Python tooling convention for a
feature this small.

---

## Sources

- `infra/DEPLOY.md` § 0.1, § 0.2, § 5 — provider registration, region sweep
  technique, CI role scope
- `docs/exam-notes/foundry-cost-model.md` §§ 2–6 — the constraints this
  feature satisfies and the baseline pricing this research corrects against
  live quota
- [Observability in Generative AI - Microsoft Foundry][obs] — tracing built on
  OpenTelemetry + Application Insights, retention/billing follows App
  Insights/Log Analytics
- [Set Up Tracing for AI Agents in Microsoft Foundry][trace] — connection
  mechanism, required RBAC, client-side SDK instrumentation
- [`connection-application-insights.bicep`][sample], `microsoft-foundry/foundry-samples` —
  the `connections` resource shape (not yet independently what-if'd — see R3, R6)
- Azure Retail Prices API, `EUR`, `swedencentral`, queried this session —
  `gpt-4.1-mini`, `gpt-5-mini`, `gpt-4o` pricing in R4
- `az cognitiveservices usage list -l swedencentral`, this session — quota
  figures in R4
- Web search, this session — Prompty format and Prompt Flow retirement date
  (R7)

[obs]: https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/observability
[trace]: https://learn.microsoft.com/en-us/azure/ai-foundry/observability/how-to/trace-agent-setup
[sample]: https://github.com/microsoft-foundry/foundry-samples/blob/main/infrastructure/infrastructure-setup-bicep/01-connections/connection-application-insights.bicep
