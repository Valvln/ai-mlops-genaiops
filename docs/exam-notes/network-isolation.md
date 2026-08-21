# Network isolation for Azure ML and Foundry — documented, not measured

**Status: nothing in this note has been deployed.** No managed virtual network,
no private endpoint and no private DNS zone has ever existed in this
subscription. `infra/main.bicep` pins `managedNetwork.isolationMode: 'Disabled'`
and `infra/foundry.bicep` pins `publicNetworkAccess: 'Enabled'`, which are the
two decisions this topic is *about* — so the repository has already met the
subject, from the side of refusing it.

Every behavioural claim below comes from the Microsoft Learn pages listed under
*Sources*, read on **2026-08-21**. Every price comes from the public retail
prices API, queried on **2026-08-21** in EUR; where a figure is not obtainable
that way it is marked **not verifiable**, not estimated. That constraint is the
reason this entry stays theory: the components here bill at rest, and the number
is what decides whether an exercise is affordable, not an impression of one.

---

## 0. How to reproduce every price here

Public retail prices — no authentication, no subscription touched:

```bash
# Azure Firewall, all meters, in EUR, for this project's region.
curl -s "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode='EUR'&\$filter=serviceName%20eq%20'Azure%20Firewall'%20and%20armRegionName%20eq%20'northeurope'"

# Private endpoint. Note the filter: serviceName is 'Virtual Network', not
# 'Azure Private Link', and the meter has NO regional row for northeurope —
# it is priced on a row whose armRegionName is 'Global'. Filtering by region
# returns zero items and looks like the meter does not exist.
curl -s "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode='EUR'&\$filter=productName%20eq%20'Virtual%20Network%20Private%20Link'"

# Private DNS zones and private DNS queries.
curl -s "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode='EUR'&\$filter=serviceName%20eq%20'Azure%20DNS'"
```

Conversions below are arithmetic on the hourly rate: the daily column is × 24,
the 30-day column is × 720. Where a figure from `compute-cost-model.md` is
quoted for comparison, that note's 730-hour month is used and said so.

---

## 1. What this repository already decided, and why

`infra/main.bicep` does not leave the isolation mode to the platform:

```bicep
// Declared rather than left to the service default: an isolation mode of
// AllowOnlyApprovedOutbound provisions a managed Azure Firewall, billed
// hourly whether or not anything uses it. what-if does not reveal the
// default, so it is pinned here instead of discovered after the fact.
managedNetwork: {
  isolationMode: 'Disabled'
}
```

`README.md` § *The first deployment* records why that line exists at all — it
was one of two defects latent in a template that compiled without a warning and
passed CI:

> **`managedNetwork` was left to a service default I had never actually seen.**
> I assumed `what-if` would reveal it. It does not: `what-if` renders what the
> template declares, not what the resource provider applies at creation time.
> The stake was not academic — `AllowOnlyApprovedOutbound` provisions a managed
> firewall billed hourly whether or not anything uses it. The template now pins
> `Disabled` explicitly.

`infra/foundry.bicep` makes the same move on the other resource, for the same
stated reason: *"an isolation default that moves underneath the template becomes
either a cost (a managed network) or a connectivity failure, discovered at the
worst moment."*

**One refinement the documentation adds, and it sharpens the claim rather than
retiring it.** Learn is explicit that the firewall is not created by choosing
the isolation mode:

> The firewall isn't created until you add an outbound FQDN rule.

So the precise sequence is: `AllowOnlyApprovedOutbound` is the only mode in
which an FQDN outbound rule can exist, and the first FQDN rule is what deploys
the Azure Firewall. The mode arms the cost; a rule fires it. The decision to pin
`Disabled` is unaffected, and § 2 explains why it is in fact *more* load-bearing
than the original reasoning assumed: the mode is a one-way door.

---

## 2. The managed virtual network, and the three modes

Enabling managed network isolation makes the workspace create and own a virtual
network. Managed compute created by that workspace lands inside it. The customer
never sees the VNet as a resource in the resource group — it is Microsoft-managed,
and it is **deleted when the workspace is deleted**.

| `isolationMode` | Outbound | What it provisions |
| --- | --- | --- |
| `Disabled` | unrestricted, in and out | **nothing.** No managed VNet at all. Either you are not isolating, or you are doing it yourself with your own VNet. |
| `AllowInternetOutbound` | all internet outbound allowed | the managed VNet, plus private endpoints to the workspace's own storage / vault / registry **only if those are flagged private** |
| `AllowOnlyApprovedOutbound` | only what a rule allows | the managed VNet, private endpoints to the workspace's default storage, registry and vault **always**, and an **Azure Firewall on the first FQDN rule** |

Three properties of this table matter more than the table:

- **The managed VNet feature itself is free.** Learn says so in as many words.
  What bills is what it provisions on your behalf — private endpoints, and the
  firewall. This is the same shape as the Foundry hub in
  `foundry-cost-model.md` § 1b: a free wrapper whose dependencies are not free.
- **It is a one-way door.** Once enabled, isolation cannot be disabled. Once set
  to `AllowInternetOutbound`, it cannot go back to `Disabled`; once set to
  `AllowOnlyApprovedOutbound`, it cannot go back to `AllowInternetOutbound`. The
  only exit is deleting the workspace. `infra/DEPLOY.md` § 3 records that this
  workspace reports `changeableIsolationModes: [AllowInternetOutbound,
  AllowOnlyApprovedOutbound]` — the ratchet turns one way, and `Disabled` is the
  only position from which either destination is still reachable.
- **Provisioning is deferred.** The managed VNet is not built at workspace
  creation; it is built when the first compute is created, or when
  `az ml workspace provision-network` is run, or at creation if
  `provision_network_now` is set. Automatic provisioning adds **~30 minutes** to
  the first compute creation, and the first FQDN rule adds **~10 more**. Billing
  for the network resources starts at provisioning, not at workspace creation —
  which means a workspace can sit in an isolation mode for weeks costing
  nothing, and then start billing the moment someone creates a compute instance.

### Outbound rule types

Three kinds, and which mode accepts them is exam-shaped:

| Rule type | Available in | Implemented by | Bills |
| --- | --- | --- | --- |
| **Private endpoint** | both isolation modes | Azure Private Link | per endpoint, per hour |
| **Service tag** | `AllowOnlyApprovedOutbound` | NSG rules in the managed VNet | no |
| **FQDN** | `AllowOnlyApprovedOutbound` | **Azure Firewall** | per hour, from the first rule |

Constraints worth carrying: FQDN rules support **ports 80 and 443 only**; in
`AllowOnlyApprovedOutbound` an FQDN rule **cannot** be used to reach an Azure
Storage account — a private endpoint is required instead; and adding an FQDN
rule weakens the data-exfiltration protection that the approved-outbound mode
otherwise provides automatically. The cheap rule type (service tag) and the
free-of-firewall rule type (private endpoint) cover most of what a workspace
actually needs; FQDN is the expensive one and is also the one that erodes the
guarantee you turned the mode on for.

The firewall SKU is selectable — `firewall_sku: standard` (the default) or
`basic`. **Premium is not supported** in a managed VNet, which also means URL-based
filtering is unavailable, since that is a Premium-only feature.

---

## 3. Private endpoints and Private Link

A private endpoint is a NIC in *your* subnet holding a private IP that maps to
one sub-resource of one PaaS instance. Traffic to it stays on the Azure
backbone. The vocabulary the exam leans on:

- **Private Link** is the service; **private endpoint** is the resource you
  create; **`groupId` / sub-resource** is which face of the target you are
  connecting to. An Azure ML workspace's sub-resource is `amlworkspace`; a
  Foundry account's is `account`; storage has `blob`, `file`, `table`, `queue`,
  `dfs`, `web` — a separate endpoint per face.
- **A connection must be Approved to carry traffic.** Creating the endpoint
  raises a consent request on the target resource; it stays `Pending` unless the
  creator has approval rights on the target. This is a two-resource, two-RBAC
  operation, and the usual failure is a network that "exists" but is `Pending`.
- **A private endpoint does not close the public door.** Both the ML and the
  Foundry documentation say it explicitly: removing private endpoints does not
  make a resource public, and enabling public access does not remove private
  endpoints. Inbound public exposure is governed by `publicNetworkAccess`
  (§ 5) and by nothing else.
- **Securing the workspace does not secure its dependencies.** Learn's warning
  is blunt: *"if you use a private endpoint for the workspace, but your Azure
  Storage Account isn't behind the virtual network, traffic between the
  workspace and storage doesn't use the virtual network for security."* Real
  isolation for this repository's baseline would be five endpoints, not one —
  workspace, storage blob, storage file, vault, registry.
- **Control plane is unaffected.** Deleting a workspace, creating a compute
  target, or any ARM management call still goes over the public internet. Only
  data-plane operations — studio, SDK, published pipelines — use the private
  endpoint. That is the same control-plane / data-plane split that
  `online-endpoints.md` § 3 records for authentication, appearing here as a
  networking fact.

---

## 4. Public network access

`publicNetworkAccess` is a property of the resource, not of the network, and it
has three practical positions on an ML workspace:

| Setting | Effect |
| --- | --- |
| `Enabled` | reachable from any internet client that authenticates |
| `Enabled` + `network_acls` | reachable only from listed public IPv4 addresses or CIDR ranges (max 200 rules) |
| `Disabled` | no public data-plane access at all; reachable only via private endpoint |

Foundry exposes the same three states through `networkAcls.defaultAction`
(`Allow` / `Deny`) plus IP and VNet rules, with **100 rules of each kind** per
account, and a `networkAcls.bypass: AzureServices` exception for a fixed trusted
list (Foundry Tools, Azure AI Search, Azure Machine Learning).

Two traps:

- **Selected-IP alone is not a configuration.** Learn warns that setting
  selected IPs *without* either a managed VNet or a workspace private endpoint
  causes compute instance provisioning to fail. The IP list restricts the front
  door; it does not give the compute a path in.
- **`Deny` with no rules denies everything, including the portal.** On the
  Foundry side, "Selected Networks and Private Endpoints" with nothing selected
  is a total data-plane block; the control plane still works, so the resource
  looks healthy while every request fails.

`infra/foundry.bicep` sits at `Enabled` deliberately, and the comment says why:
*"The harness runs from a laptop, so public access is what it needs."* The
authentication story is carried by `disableLocalAuth: true` and Entra tokens
instead — identity doing the work that network isolation would otherwise do.

---

## 5. Private DNS zones

This is the part that makes private endpoints actually work, and the part that
silently doesn't.

When a private endpoint is created, Azure rewrites the resource's public DNS
record to a CNAME pointing into a `privatelink.*` subdomain. Resolving that name
from **outside** the VNet still yields the public IP. Resolving it from **inside**
a VNet linked to the matching private DNS zone yields the endpoint's private IP.
The connection string never changes — which is the design goal, and also why a
misconfigured zone produces a working-looking client that is quietly talking to
the public endpoint.

Zones this repository's resources would need, with sub-resource:

| Resource | Sub-resource | Private DNS zone |
| --- | --- | --- |
| ML workspace | `amlworkspace` | `privatelink.api.azureml.ms` **and** `privatelink.notebooks.azure.net` |
| Foundry account | `account` | `privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com`, `privatelink.services.ai.azure.com` |
| Storage account | `blob`, `file` | `privatelink.blob.core.windows.net`, `privatelink.file.core.windows.net` |
| Key Vault | `vault` | `privatelink.vaultcore.azure.net` |
| Container registry | `registry` | `privatelink.azurecr.io` |

Mechanics that decide whether it works:

- **A zone does nothing until it is linked to a virtual network.** Creating the
  zone and creating the vnet-link are two operations.
- **The private DNS zone group** is the object that binds zone to endpoint and
  keeps the A records correct. Limits: **five zones per group**, one zone per
  zone-name, and **one group per private endpoint**.
- **The automatic zone creation only happens if you use the documented zone
  names.** A zone named anything else is inert.
- **Don't share a zone between two services.** Learn warns that pointing one
  zone at two different services' endpoints deletes the first A record.
- **Custom or on-premises DNS forwards to the *public* suffix**, not the
  privatelink one — `api.azureml.ms`, not `privatelink.api.azureml.ms`.
- **A resolvable public name proves nothing about access.** The `privatelink`
  CNAME chain is deliberately resolvable from the internet, so hybrid clients
  keep working. Access is decided by `publicNetworkAccess` and the service
  firewall, at the front door, regardless of what DNS returned.

This repository's baseline would need **eight** zones for the five resources
above — which is why § 7 prices zones per unit rather than as a rounding error.

---

## 6. What changes for a Foundry resource

A Foundry account is a `Microsoft.CognitiveServices/accounts` resource, not a
`Microsoft.MachineLearningServices/workspaces` one, and the differences follow
from that:

| | ML workspace | Foundry resource |
| --- | --- | --- |
| Inbound | private endpoint, sub-resource `amlworkspace` | private endpoint, sub-resource `account` (labelled "account" in the portal) |
| Public access control | `publicNetworkAccess` + `network_acls` | `publicNetworkAccess` + `networkAcls` (defaultAction, IP rules, VNet rules, `bypass`) |
| Outbound | **managed VNet** owned by the platform, with isolation modes | **VNet injection**: a subnet *you* own, delegated to `Microsoft.App/environments`, **/27 or larger** |
| Compute you manage | clusters, instances, endpoints inside the managed VNet | none — the Agent client is container-injected into your subnet |
| Egress control | built-in isolation modes, optional managed firewall | **your own** firewall, typically hub-and-spoke; nothing is provisioned for you |
| Dependency endpoints | some created automatically by the managed VNet | **none.** Private endpoints to Storage, AI Search and Cosmos DB are explicitly *not* auto-created |
| Reversibility | isolation cannot be turned off; modes ratchet one way | outbound networking **cannot be changed at all** — the delegated subnet is fixed, and adding injection to an existing resource requires a redeploy |

The conceptual shift: Azure ML's managed VNet is **the platform renting you an
isolated network**, and it charges you for the firewall and endpoints it creates
inside it. Foundry's injection model is **you lending the platform a subnet**,
and every billed component — firewall, private endpoints, DNS zones — is one you
created and one you can see. Neither is cheaper by nature; Foundry is simply
honest earlier about which line items are yours.

The custom subdomain matters twice over here. `infra/foundry.bicep` already sets
`customSubDomainName` because Entra token auth requires it; the private-link
documentation adds a second reason — clients must call the custom subdomain, and
must **not** call the internal `*.privatelink.openai.azure.com` name, which is
only an intermediate CNAME.

One limitation worth remembering because it contradicts the marketing: several
Foundry agent tools reach the public internet even in a fully network-isolated
deployment — Bing Grounding, Websearch and SharePoint Grounding are documented as
"Public endpoint". Network isolation for Foundry is not all-or-nothing, and the
tool table is where the exceptions live.

---

## 7. The price of every component that bills at rest

EUR, retail, `northeurope` unless the meter is global, read **2026-08-21**.

| Component | Meter | Rate | Per day | Per 30 days |
| --- | --- | --- | --- | --- |
| **Azure Firewall, Standard** | `Standard Deployment` | **1.098274 €/hour** | 26.36 € | **791 €** |
| Azure Firewall, Standard — throughput | `Standard Capacity Unit` | 0.061503 €/hour each | — | — |
| Azure Firewall, Standard — traffic | `Standard Data Processed` | 0.014058 €/GB | — | — |
| **Azure Firewall, Basic** | `Basic Deployment` | **0.347054 €/hour** | 8.33 € | **250 €** |
| Azure Firewall, Basic — traffic | `Basic Data Processed` | 0.05711 €/GB | — | — |
| **Private endpoint** | `Standard Private Endpoint` | **0.008786 €/hour** | 0.21 € | **6.33 €** |
| Private endpoint — traffic | `Standard Data Processed`, ingress and egress | 0.008786 €/GB, tiering to 0.005272 then 0.003514 | — | — |
| **Private DNS zone** | `Private Zone` | **0.439309 € per zone** (first 25; 0.087862 € beyond) | — | see below |
| Private DNS queries | `Private Queries` | 0.351448 € per 1M | — | — |
| Private DNS record sets | `Private Record Set` | 0.0 € for the first tier, 0.001318 € beyond | — | — |
| Managed virtual network (the feature) | — | **free**, per Learn | 0 | 0 |
| The virtual network itself, NSGs, service tags, service endpoints | — | **free** | 0 | 0 |

**Not verifiable from the API, and therefore not asserted:**

- **The billing period of the private DNS zone meter.** `Private Zone` returns
  `unitOfMeasure: "1"` with no time dimension and no `armRegionName`. The
  quantity is a zone, but *per what* is not in the response. The Azure DNS
  pricing page treats it as monthly; the API does not say so, so the figure
  above is written per zone and the monthly total is left uncomputed. Reading it
  as monthly makes this repository's eight zones ≈3.51 €/month — which is the
  right order of magnitude to remember and the wrong number to quote.
- **How many firewall capacity units a managed VNet provisions.** The
  `Standard Deployment` charge is the floor and is certain. Capacity units scale
  with throughput and are billed on top; nothing in the price list or in the
  managed-network documentation states the baseline count for a workspace-managed
  firewall. The 791 €/month figure is therefore a **minimum**, not a total.
- **Whether the managed VNet's own private endpoints bill at the same rate as
  customer-created ones.** They are Private Link resources and the documentation
  points at Private Link pricing, so they almost certainly do — but "almost
  certainly" is exactly the class of claim `compute-cost-model.md` § 7 exists to
  quarantine, and it is settled by a bill, not by an inference.

### What this means in one line

A Standard managed firewall idling for 30 days costs ≈791 € — about what a
`Standard_DS1_v2` managed online endpoint would cost running continuously for
**eighteen months** at the 0.06 €/hour rate `compute-cost-model.md` § 4.3
measured. Basic is a third of that and still ≈250 €. The deployed baseline in
this repository costs approximately nothing at rest (`README.md`, checked in
Cost Management); one FQDN rule typed into a portal blade would make the network
the largest line item this subscription has ever carried, by orders of
magnitude.

Private endpoints, by contrast, are almost affordable: five endpoints for the
baseline's five resources is ≈31.65 €/month — real money for a study project,
but a defensible one-afternoon exercise if they were deleted the same day
(five endpoints for five hours is ≈0.22 €). It is the **firewall** that makes
`AllowOnlyApprovedOutbound` unaffordable, not isolation as such.

---

## 8. A private endpoint in Bicep — NOT DEPLOYED

This block is documentation. It is inside this note, and deliberately not in
`infra/`, because a template that compiles and has never been deployed is
exactly the artifact this repository has learned to distrust: `az bicep build`
proves syntax, not that a resource can be created, and two defects already
reached `main` that way. It has not been compiled, deployed, or `what-if`-ed.

```bicep
// NOT DEPLOYED. Illustrative only — no az bicep build has been run against
// this, and no deployment has ever created these resources. It is here to
// show the shape of the three objects a working private endpoint needs.

// 1. The endpoint: a NIC in your subnet, bound to ONE sub-resource.
resource workspacePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${workspaceName}'
  location: location
  properties: {
    // The subnet must have private endpoint network policies disabled.
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${workspaceName}'
        properties: {
          privateLinkServiceId: mlWorkspace.id
          // The sub-resource. 'amlworkspace' for a workspace; 'account' for a
          // Foundry resource; 'blob' / 'file' / 'vault' / 'registry' for the
          // dependencies. One endpoint reaches one face of one resource.
          groupIds: [ 'amlworkspace' ]
        }
      }
    ]
  }
}

// 2. The zone, and its link to the VNet. The zone alone resolves nothing:
//    without the vnet link, clients in the VNet never consult it.
resource apiZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  // The name is not a label. Automatic record management only happens for
  // the documented zone name; anything else is an inert zone.
  name: 'privatelink.api.azureml.ms'
  location: 'global'
}

resource apiZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: apiZone
  name: 'link-${vnetName}'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    // false: this zone resolves private endpoints, it does not register VMs.
    registrationEnabled: false
  }
}

// 3. The zone group: what keeps the A records correct as the endpoint changes,
//    and what deletes them when the endpoint is deleted. Max five zones per
//    group, and only one group per endpoint — so a workspace, which needs both
//    the api and the notebooks zone, puts both in this single group.
resource zoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: workspacePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'api'
        properties: {
          privateDnsZoneId: apiZone.id
        }
      }
      {
        name: 'notebooks'
        properties: {
          // A second zone resource, declared the same way as apiZone above.
          privateDnsZoneId: notebooksZone.id
        }
      }
    ]
  }
}
```

Three things this shape makes visible that prose does not: the endpoint names
its sub-resource and only that one, the zone name is functional rather than
cosmetic, and the DNS half is **three** resources per zone, not one. A study
exercise that creates "a private endpoint" is really creating six or seven
objects, and forgetting the zone group is how it ends up resolving to a public
IP while looking finished.

---

## 9. What this note would cost to verify, and what it would not

**Affordable, if deleted the same day.** A VNet, a subnet, one private endpoint
on the existing workspace, two DNS zones with links and a zone group: the only
metered items are one endpoint at 0.008786 €/hour and two zones. A four-hour
exercise is **cents**, plus whatever the zones prove to cost for a partial
month. The one caveat is that verification needs a client *inside* the VNet to
mean anything — resolving from a laptop returns the public IP by design, so a
real check needs a VM or Bastion, and that reintroduces compute billing.

**Not affordable.** Provisioning a managed VNet in `AllowOnlyApprovedOutbound`
and adding one FQDN rule, to watch the firewall appear, costs 1.098274 €/hour at
Standard for as long as it exists, and it cannot be undone: the isolation mode
never returns to `Disabled`, so the only teardown is deleting the workspace —
which in this repository collides with the 90-day Key Vault purge-protection
lock recorded in `infra/DEPLOY.md`. The experiment would cost a workspace, not
just euros.

So the verified-versus-documented line for this topic falls here: private
endpoints and DNS are cheap enough to prove and worth proving; the firewall is
the one component this project should know entirely from documentation, and
`main.bicep` should keep saying `Disabled`.

---

## Sources

- [Managed virtual network isolation (Azure Machine Learning)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-managed-network) — read 2026-08-21
- [Configure a private endpoint for an Azure Machine Learning workspace](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-configure-private-link) — read 2026-08-21
- [How to configure network isolation for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link) — read 2026-08-21
- [Configure virtual networks for Foundry Tools](https://learn.microsoft.com/en-us/azure/ai-services/cognitive-services-virtual-networks) — read 2026-08-21
- [Azure Private Endpoint private DNS zone values](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns) — read 2026-08-21
- [Azure Private Endpoint DNS integration scenarios](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns-integration) — read 2026-08-21
- [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) — queried 2026-08-21, EUR
- `infra/main.bicep`, `infra/foundry.bicep`, `infra/DEPLOY.md` § 1 and § 3, `README.md` § *The first deployment* — the decisions quoted in § 1
- `compute-cost-model.md` § 4.3, `foundry-cost-model.md` § 1b — the comparisons in § 7
