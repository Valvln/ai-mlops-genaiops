# Quota and rate limits — a subscription allocation, not a regional one

**Status: met head-on, and the conclusion drawn at the time is now out of date.**
Feature 006 discovered that `gpt-5-nano` was listed in `swedencentral` and still
undeployable, because this subscription had **quota 0** for that meter. The
observation stands. The model it produced — *quota is allocated per region* — is
the thing this note exists to correct.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-08-21**.

---

## 1. Where quota lives

> «Quotas and limits **aren't enforced at the tenant level**. Instead, the
> highest level of quota restrictions is scoped at the **Azure subscription
> level**.»

That is the fixed point. Everything else — region, resource, deployment — is a
subdivision of a subscription's allocation, and which subdivision applies has
changed.

---

## 2. Subscription-level quota management (after 7 May 2026)

> «Foundry tracks quota for deployments **at the subscription level rather than
> per resource or per region**. All resources and regions in a subscription share
> the same quota pool.»

The consolidation, precisely:

| Deployment type | Pool |
| --- | --- |
| **Global Standard** | deployments of the **same model and version** share **one pool across all regions** in the subscription |
| **Data Zone Standard** | deployments of the same model and version share **one pool per data zone** (US, EU, APAC) |

Existing approved quota is retained and applies automatically at the subscription
level — no action required.

### How to tell which regime applies to a model

The rollout is per model, starting with Realtime Translate and Realtime
Transcribe and extending to the rest. The **Scope** column on the Foundry
portal's Quota page is the answer:

| Scope column shows | Regime |
| --- | --- |
| `Global` or `Data Zone` | subscription-level quota management |
| a region name (e.g. `East US`) | **per-region** quota, for that subscription and model |

So both regimes are live simultaneously and the portal tells you which one you
are in. "Quota is per region" is not wrong — it is *no longer the default answer*,
and the page you check to find out is named.

### When a model is upgraded

The new Global or Data Zone limit is set to the **greater of**:

- the applicable tier limit, or
- the **total quota assigned to all existing deployments** of that model within
  the quota scope.

Five regional Global Standard deployments therefore do not lose quota by
consolidating; if their combined quota exceeds the tier limit, the combined
figure becomes the new limit.

### Models not yet onboarded

For those, the older rule still reads:

> «Tokens per minute (TPM) and requests per minute (RPM) limits are defined **per
> region, per subscription, and per model or deployment type**.»

---

## 3. Quota tiers, and automatic escalation

Seven tiers: **Free Tier and Tiers 1 through 6**, Tier 6 highest. The initial
tier is based on current usage of that model and on the customer's relationship
with Microsoft — Enterprise Agreement or MCA-E status raises it.

- **Quotas increase automatically with usage.** If usage grows to the point where
  the current tier limits it, the system upgrades to the next tier. Payment
  history is also considered.
- **You can opt out**, with `tierUpgradePolicy: "NoAutoUpgrade"` via a PATCH on
  `.../providers/Microsoft.CognitiveServices/quotaTiers/default`. Learn's stated
  reason for the opt-out is blunt and worth remembering: *some customers use
  quota to manage their billing*, which «isn't the Azure best practice» but is a
  real configuration people have. The opt-out is preview.
- **You can still request more.** An approved request keeps the tier and assigns
  more quota within it.
- Check the current tier with the control-plane API, `GET
  .../providers/Microsoft.CognitiveServices/quotaTiers?api-version=…`.

### The TPM-to-RPM ratio is not a constant

A widespread piece of folklore says "6 RPM per 1,000 TPM". Learn's own footnote
on the tier tables shows the ratio is set **per model and per version**:

> «Versions `2026-05-05`, `2026-05-28`, and `2026-06-24` use **10 RPM per 1,000
> TPM**. Version `2026-08-06` uses **1 RPM per 1,000 TPM**, so the tables list the
> versions separately.»

Two versions of the *same model name* with a tenfold difference in request
allowance for identical token allowance. **Read the table; do not compute the
ratio.**

Some models are rated in a **10-second** window instead of a minute (`300 / 10s`),
and image models are rated in RPM only, with no TPM figure at all.

---

## 4. Default rate limits for non-Azure-OpenAI models

| Models | TPM | RPM | Concurrent |
| --- | --- | --- | --- |
| DeepSeek-R1, DeepSeek-V3-0324 | 5,000,000 | 5,000 | 300 |
| Llama 3.3 70B, Llama-4-Maverick, Grok 3, Grok 3 mini | 400,000 | 1,000 | 300 |
| **Rest of models** | **400,000** | **1,000** | **300** |
| Azure OpenAI models | varies per model and SKU — see the tier tables | | |

Quota increases are available for Foundry Models sold by Azure, Azure OpenAI
models and Anthropic models. **Other partner and community models don't support
quota increases at all** — for those, the default is the ceiling.

---

## 5. ⚠️ Quota is not availability

The two failures look identical from a failed `az deployment` and are on adjacent
rows of Learn's troubleshooting table:

| Symptom | Cause | Resolution |
| --- | --- | --- |
| **Quota exceeded** | «Subscription limit reached for tokens per minute» | request an increase, or use a different region |
| **Model not available in region** | «Model isn't deployed or supported in the selected region» | check model availability and choose an available region |
| **Quota page shows 0 available** | «Subscription or regional quota fully allocated» | **move unused quota from another deployment**, or request an increase |

The third row carries the move that people forget exists: **quota can be
reallocated between deployments**, not only requested. Learn repeats it in the
best-practices list — «Increase the quota assigned to your deployment. **Move
quota from another deployment, if necessary.**»

**This is the correction to feature 006's conclusion.** The catalogue said
`gpt-5-nano` existed as `GlobalStandard` in `swedencentral`; the deployment was
refused; the meter read 0. That was the *first* row, not the second — an
allocation of zero on a subscription, not an absence from a region. The two are
different objects with different remedies, and only one of them is fixed by
changing region.

### Reading it programmatically

Two complementary REST APIs, both read-only:

- the **Usages API** — consumption against limits
- the **Model Capacities API** — available deployment capacity by model and region

One caveat that will waste an afternoon: «both the Foundry portal and the
capacity APIs return quota and capacity information for models that are
**retired** and no longer available for new deployments.» A healthy quota figure
is not proof that a model can be deployed.

A second one, measured here rather than documented: `az cognitiveservices usage
list` spells the same model **`gpt4.1-mini` for standard SKUs and `gpt-4.1-mini`
for batch ones**, so a query filtered on the real model name reports healthy
quota for a SKU nobody is deploying. That is a repository observation, not a
Learn claim — `genaiops/foundry-block3/README.md` is its provenance.

---

## 6. HTTP 429, and why it fires below quota

The troubleshooting row is unambiguous about the remedy:

> «**HTTP 429 Too Many Requests** — Token-per-minute or request-per-minute limit
> exceeded — Implement retry logic with exponential backoff. **Use the
> `Retry-After` header value.**»

And the counter-intuitive case is documented rather than denied:

> «You might receive **429 (Too Many Requests)** responses **even when token usage
> metrics appear below your quota**.»

So a 429 with green-looking metrics is not a service defect and not a reason to
open a ticket. The portal's aggregated token metrics are not the window the
service enforces against, and RPM is a second limit that TPM dashboards don't
show.

**HTTP 431** is the other numeric worth recognising: more than 10 custom headers.

### Usage tiers and latency

Distinct from quota tiers, and easy to conflate. A **usage tier** is the level of
throughput below which latency stays predictable. Usage is defined **per model**
as «the total tokens consumed across **all deployments in all subscriptions in all
regions for a given tenant**» — tenant-wide, unlike quota.

Exceeding it doesn't produce an error; it produces variance — «latency can vary
and, in some cases, may be more than **two times higher**». Usage tiers apply to
Standard, Data Zone Standard and Global Standard **only** — not to global batch,
not to provisioned.

### Staying inside the limits

- implement retry logic
- avoid sharp changes in workload; increase gradually
- test different load-increase patterns
- increase or **move** the quota assigned to the deployment

---

## 7. Client-side timeouts

Not quota, but the same failure surface, and explicitly documented because the
defaults come from whichever library you use and «might not be the same limits»:

| Case | Documented ceiling |
| --- | --- |
| Reasoning models | up to **29 minutes** |
| Non-reasoning, streaming | up to **60 seconds** |
| Non-reasoning, non-streaming | up to **29 minutes** |

Set a timeout **below** these, tuned to actual traffic. For reasoning models all
reasoning tokens are generated and then summarised **before the first response
token is sent**, which is why streaming does not shorten the wait there; the
`reasoning effort` parameter is the lever that does.

---

## 8. What this note would cost to verify

**Reading quota is free and touches no resource.** `az cognitiveservices usage
list`, the Usages API and the Model Capacities API are read-only and need no
existing account. The Foundry portal's Quota page — including the **Scope**
column that decides § 2 — is free to look at.

**Provoking a 429 is nearly free but is a genuinely useful lab**, and it is the
one thing in this note that has never been observed here: a loop that exceeds RPM
on a `GlobalStandard` nano model costs a fraction of a cent and produces the
`Retry-After` header, which is the fact that matters. Everything else in § 6 is
read.

The unverifiable part stays unverifiable: **whether this subscription's tier
would auto-upgrade**, since that depends on sustained consumption this project
will never generate.

---

## Sources

- [Microsoft Foundry Models quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/quotas-limits) — read 2026-08-21; §§ 1, 2, 4, 5
- [Azure OpenAI quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/quotas-limits) — read 2026-08-21; §§ 3, 6, 7, and the batch quota tables
- [Understanding deployment types](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/deployment-types) — read 2026-08-21; the troubleshooting table in § 5
- `foundry-deployment-types.md` § 5 — enqueued-token quota for batch
- `genaiops/foundry-block3/README.md` — the `gpt-5-nano` observation and the CLI naming quirk in § 5
