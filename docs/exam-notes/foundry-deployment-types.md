# Deployment types for Foundry Models — what each bills, and where it processes

**Status: one deployment type has been exercised.** Feature 006 deployed
`gpt-4.1-mini` `2025-04-14` as **`GlobalStandard`** with capacity 1, and nothing
else. Provisioned, batch, data zone and developer deployments are documented
here and have never been created — deliberately, for the reason
`foundry-cost-model.md` § 3 sets out.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-08-21**. Prices live in `foundry-cost-model.md` § 3 and § 4 and
are not restated.

---

## 1. What a deployment type actually decides

Three things, and only three:

- **Where your data is processed** — global, data zone, or single region
- **How you pay** — pay-per-token or reserved capacity
- **Performance characteristics** — latency variance, throughput limits

These types apply to the **Serverless API** deployment option only. Open-source
and custom models on **managed compute don't use them at all** — managed compute
has its own resource type and its own control-plane operations
(`foundry-rbac-and-authentication.md` § 6).

There is also a fourth path that isn't a deployment type: **instant access
(preview)** lets you call supported models by name with no deployment created.

---

## 2. The nine SKU codes

The SKU code is the string that appears in Bicep, in `az cognitiveservices`
output and in Azure Policy. **Learning the marketing name without the code is
how § 3 goes wrong.**

| Deployment type | SKU code | Data processing | Billing |
| --- | --- | --- | --- |
| Global Standard | `GlobalStandard` | any Azure region | pay-per-token |
| Global Provisioned | `GlobalProvisionedManaged` | any Azure region | reserved PTU |
| Global Batch | `GlobalBatch` | any Azure region | 50% discount, 24-hr |
| Data Zone Standard | `DataZoneStandard` | within the data zone | pay-per-token |
| Data Zone Provisioned | `DataZoneProvisionedManaged` | within the data zone | reserved PTU |
| Data Zone Batch | `DataZoneBatch` | within the data zone | 50% discount |
| Standard | `Standard` | **single region** | pay-per-token |
| Regional Provisioned | **`ProvisionedManaged`** | **single region** | reserved PTU |
| Developer | `DeveloperTier` | any Azure region | pay-per-token |

### ⚠️ The naming trap

**`ProvisionedManaged` is the *regional* provisioned type.** The global one is
`GlobalProvisionedManaged`, and `RegionalProvisionedManaged` does not exist.
Symmetrically, the bare `Standard` is the *single-region* pay-per-token type,
not the default one — the default is `GlobalStandard`.

`foundry-cost-model.md` § 3b tabulates the three provisioned tiers by price
under their marketing names (Global / Data Zone / Regional Provisioned) and
never binds them to SKU codes. This table is that missing half.

---

## 3. Data residency: at rest versus in flight

The single most quotable paragraph in the topic, and the one that catches people
who assume "global" means "your data leaves the geography":

> «**Data stored at rest remains in the designated Azure geography.** However,
> inferencing data is processed as follows:
> - **Global** types: May be processed in any Azure region
> - **Data Zone** types: The service processes data only within the
>   Microsoft-specified data zone (US, EU, or Asia Pacific)
> - **Standard (single region)** types: The service processes data in the
>   deployment region.»

So the correct answer to "does `GlobalStandard` move our data?" is: **the data at
rest does not move; the inference traffic can.** Two different questions, two
different answers, one sentence apart in the documentation.

The data zones themselves:

- **United States** — anywhere within the US
- **European Union** — within the Azure EU Data Boundary, which can include
  EFTA countries such as Norway and Switzerland in addition to EU member states
- **Asia Pacific** — multiple APAC regions

Microsoft **can add regions to either data zone without prior notice**. A data
zone is a compliance boundary, not a fixed list you can pin.

---

## 4. Global Standard is the documented default

> «For most workloads, start with **Global Standard**. It launches first when a
> new model releases, has the lowest price, and offers the broadest region
> coverage. **Move to another deployment type only when you have a specific
> reason**, such as data residency, reserved throughput, or asynchronous batch
> processing.»

And the release order is documented, which is why "the newest model on a
single-region deployment" is often simply unavailable:

> «New deployment types become available in a set order: **Global, then Data
> Zone, then single region.** Single-region deployment types arrive last, have no
> guaranteed availability date, and depend on capacity that frees up as older
> models retire.»

### The selection table

| Requirement | Type |
| --- | --- |
| Default: newest models, lowest price, broadest regions | Global Standard |
| Reserved, predictable throughput | Global Provisioned |
| Keep processing within a data zone | Data Zone Standard or Data Zone Provisioned |
| Data residency **plus** reserved throughput | Data Zone Provisioned |
| Pin processing to a single region | Standard or Regional Provisioned |
| Large asynchronous jobs at lower cost | Global Batch or Data Zone Batch |
| Evaluate a fine-tuned model (temporary, no SLA) | Developer |
| Quick start / trying a new model | instant access (preview) — no deployment |

By latency: **provisioned** types for low latency *variance*; standard types
accept variance. By workload: variable and bursty → standard; consistent high
volume → provisioned.

---

## 5. Batch: the quota is the point, not just the discount

Global Batch and Data Zone Batch process asynchronous groups of requests at
**50% less cost than Global Standard**, with a **24-hour target turnaround**.
The operationally important part is the third property:

> «Global Batch requests have a **separate enqueued token quota**, which avoids
> any disruption of your online workloads.»

Quota is counted in **enqueued tokens**: when you submit a file, its tokens are
counted, and «until the batch job reaches a terminal state, those tokens count
against your total enqueued token limit». So a stuck job holds quota.

And the trade you are making is explicit:

> «Batch deployments trade real-time responsiveness for cost savings. Batch
> requests **don't have a real-time SLA** — they target completion within 24
> hours but might take longer.»

Batch file limits worth carrying: 500 input files without expiration (10,000 with
an expiration set), 200 MB per input file (1 GB with bring-your-own-storage),
**100,000 requests per file**.

---

## 6. Developer tier is not a cheap Standard

`DeveloperTier` looks like a bargain and is a trap for anything that must stay
up:

> «The Developer deployment type is designed for **fine-tuned model evaluation
> only**. It provides cost-efficient testing of custom models but **doesn't
> include data residency guarantees or an SLA**. Developer deployments have a
> **fixed 24-hour lifetime and are automatically deleted after expiration**.»

Three disqualifiers in one paragraph: purpose, guarantees, lifetime. Fine for a
throwaway evaluation of a fine-tune; wrong for anything a user depends on.

---

## 7. SLA and availability, stated plainly

- **Provisioned** types: guaranteed throughput, lower latency variance.
- **Standard** types: best-effort.
- **Developer**: no SLA.
- **Batch**: no real-time SLA.

One availability fact that reads as a contradiction and isn't:

> «With Global Standard and Data Zone Standard deployment types, if the primary
> region experiences an interruption in service, **all traffic initially routed
> to this region is affected**.»

Global routing improves *capacity* and *latency consistency*; it is not, by
itself, a disaster-recovery design.

Global Standard and Data Zone Standard also support **priority processing** —
faster responses on a pay-as-you-go basis.

---

## 8. Restricting deployment types with Azure Policy

The governance lever the exam expects you to know exists. Deployments are ARM
resources of type `Microsoft.CognitiveServices/accounts/deployments`, and the SKU
name is a policy-addressable field:

```json
{
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        { "field": "type",
          "equals": "Microsoft.CognitiveServices/accounts/deployments" },
        { "field": "Microsoft.CognitiveServices/accounts/deployments/sku.name",
          "equals": "GlobalStandard" }
      ]
    }
  }
}
```

Replace the SKU name with the type you want to block. For a study subscription
the interesting inversion is blocking **`GlobalProvisionedManaged`** — a policy
is the only mechanism that stops a 13.16 €/hour deployment from being created by
a wrong click, since the subscription has no spending limit.

---

## 9. When a deployment won't create

| Symptom | Cause | Fix |
| --- | --- | --- |
| Deployment type unavailable | the model doesn't support the selected type | check model availability by deployment type |
| Quota exceeded | subscription TPM limit reached | request an increase, or use another region |
| Region unavailable | model not deployed in the selected region | pick a region from the model's availability list |
| Provisioned capacity unavailable | no PTU capacity in the region | try another region, or Global Provisioned for broader availability |

**The first two rows are different failures.** Distinguishing them is the whole
of `foundry-quota-and-rate-limits.md` § 5, and it is the mistake feature 006
walked into with `gpt-5-nano`.

---

## 10. What this note would cost to verify

**The standard types: nothing meaningful.** Creating a `GlobalStandard`
deployment and deleting it costs the tokens you send through it — feature 006
spent ~1,300 tokens building an entire block. `DataZoneStandard` and `Standard`
bill on the same meter family.

**The provisioned types: not affordable, and not close.** The floor is 15 PTU at
0.877578 €/PTU/hour for Global Provisioned — **13.16 €/hour** — and provisioned
deployments cannot be paused; billing stops only on deletion
(`foundry-cost-model.md` § 2 and § 3b). PTU is exam material to *recognise* and
to *size*, and the sizing arithmetic is free on paper.

**Batch is cheap and untested here.** A `GlobalBatch` deployment of
`gpt-4.1-nano` in `swedencentral` bills at half the standard rate and has its own
quota; it is the one untried type in this list that would cost cents to exercise,
and it is the honest next lab if this topic needs a scar rather than a note.

---

## Sources

- [Understanding deployment types in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/deployment-types) — read 2026-08-21; §§ 1–4, 6–9
- [Azure OpenAI quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/quotas-limits) — read 2026-08-21; the batch quota and file limits in § 5
- `foundry-cost-model.md` § 2, § 3, § 4 — every euro figure, the PTU floor, the model-availability-by-region table
- `genaiops/foundry-block3/README.md` — the one deployment that exists
