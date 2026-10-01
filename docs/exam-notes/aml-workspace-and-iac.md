# Azure Machine Learning workspace: resources, Bicep and CLI

**Status: built and measured for the parts this repository deploys.**
`infra/main.bicep` creates a workspace, its four associated resources, a
datastore and a compute cluster. It deploys through CI behind an approval gate.
This note restates what Learn documents about creating and managing a
workspace, so that the measured parts can be read against the source.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Create and manage a workspace*,
*Deploy Machine Learning workspaces and resources by using Bicep and Azure
CLI*. Networking is in `network-isolation.md`. CI/CD is in
`aml-github-actions-and-git.md`.

---

## 1. What a workspace is

A workspace groups jobs, experiments, data assets, models, components and
endpoints. It also holds configuration: compute targets, datastores, and
security settings for networking, identity and encryption.

Learn's organising advice:

- One workspace per project gives cost reporting per project.
- Grant access to Microsoft Entra **groups**. Group owners then manage
  membership without a role on the workspace.
- Share assets across workspaces with **registries**
  (`aml-environments-components-registries.md`).
- A **hub** workspace groups project workspaces with shared settings. Hub
  workspaces are the same resource type as Foundry hubs.

A workspace **can't be moved to another subscription**, and the owning
subscription can't be moved to a new tenant.

---

## 2. Associated resources

| Resource | Role | Constraint Learn states |
| --- | --- | --- |
| Storage account | job logs, uploads, notebooks of compute instances | default account can't be `BlobStorage`, Premium, or have hierarchical namespace; Blob and File must both be enabled |
| Container registry | images for custom environments | created **on first need** if not supplied; **never delete it** once created, the workspace becomes inoperative |
| Application Insights | monitoring of inference endpoints | if you delete the auto-created one, the only way to recreate it is to recreate the workspace |
| Key Vault | secrets used by compute and the workspace | see § 4 for template redeploys |

Premium storage or hierarchical namespace can be used as **extra** storage
through a datastore.

Workspace metadata is stored in an Azure Cosmos DB instance that Microsoft
maintains. With a **customer-managed key**, the extra resources are created in a
separate resource group in your subscription. The encryption settings, the key
vault ID and `hbi_workspace` can be set only at creation.

### Resource providers

Most providers are registered automatically, not all. The errors are *No
registered resource provider found for location* and *The subscription is not
registered to use namespace*. The list Learn gives: `MachineLearningServices`,
`Storage`, `ContainerRegistry`, `KeyVault`, `Notebooks`, `ContainerService`
(AKS), plus `DocumentDB` and `Search` for customer-managed keys, and `Network`
for a managed virtual network.

Associated resources in **another subscription** need the
`Microsoft.MachineLearningServices` namespace registered in that subscription.

---

## 3. CLI

```bash
az ml workspace create -n <ws> -g <rg>                 # creates the associated resources
az ml workspace create -g <rg> --file workspace.yml    # brings existing ones by resource ID
az ml workspace update -n <ws> -g <rg> --public-network-access enabled
az ml workspace sync-keys -n <ws> -g <rg>               # forces key resync
az ml workspace delete -n <ws> -g <rg>                  # soft delete by default
```

- In the YAML file, any associated resource you omit is created
  automatically.
- After a key rotation on an associated resource, the workspace resyncs in
  **about an hour**. `sync-keys` forces it. The same command is Learn's first
  fix for a container registry authorization failure during an image build.
- **Deleting a workspace does not delete** the storage account, key vault,
  container registry or Application Insights. They keep billing until deleted.
  Deleting the resource group removes them all.
- With private endpoints on both the registry and the workspace, Container
  Registry tasks can't build images. Set `image_build_compute` to a compute
  cluster.

---

## 4. Templates (ARM and Bicep)

Learn's quickstart template deploys storage, Key Vault, Application Insights,
Container Registry and the workspace, with two required parameters, `location`
and `workspaceName`. The points Learn makes about templates:

- **API versions.** The example template "might not always use the latest API
  version". Check the REST reference for each resource type.
- **Container registry is optional at creation.** One is created when an
  operation needs it, such as training or deploying.
- **Key Vault access policies are cleared on every redeploy.** Most template
  operations are idempotent. Key Vault is the exception: "Key Vault clears the
  access policies each time the template is used", which breaks the workspace's
  access to it. Learn's two fixes: put the existing policies into the
  template's `accessPolicies`, or reference the existing vault by ID and drop
  its creation from the template. A CI pipeline that redeploys the same template is the case Learn
  names.
- **One workspace per virtual network per template.** The template creates DNS
  zones, so it can't deploy several workspaces into the same virtual network.
- **Application Insights** isn't available everywhere. The template falls back
  to South Central US for it.

---

## 5. Deletion and recovery

Workspace delete is a **soft delete** by default. A soft-deleted workspace can be
recovered. A permanent delete can't.

The workspace's own soft delete is separate from Key Vault's. Key Vault purge
protection is irreversible once enabled, and Learn requires it for a
customer-managed-key vault.

---

## 6. What this repository measured, and what it did not

**Measured** (`infra/DEPLOY.md`, `README.md`):

- **The template compiled and failed to deploy.** The storage account name was
  25 characters against a limit of 24. `az bicep build` doesn't check name
  length; only a real deployment or `what-if` against the subscription did.
- **All five resource providers started unregistered** on this subscription.
  This matches Learn's warning in § 2.
- **The platform creates what the template does not declare.** Application
  Insights added a notification group. The container registry was created on
  first need by a custom environment build, then declared in the template on
  2026-08-20 so that the template owns it. This is § 2's "created on first
  need", observed.
- **The workspace's system-assigned identity received role assignments no
  template declared**, and the platform recreated them when deleted
  (`aml-identity-and-access.md` § 2).
- **The template uses `enableRbacAuthorization: true` on the vault.** The
  access-policy reset in § 4 doesn't apply to an RBAC vault. Redeploys of
  `main.bicep` haven't hit it.
- **Key Vault purge protection was measured irreversible** (`BadRequest`) and
  keeps the old vault name until 2026-11-16.

**Not measured:** a customer-managed key, a hub workspace, workspace soft-delete
recovery, `sync-keys`, the Key Vault access-policy reset on an access-policy
vault.

---

## 7. What this note would cost to verify

The access-policy reset needs a vault in access-policy mode and two deployments
of the same template. Storage and Key Vault at rest cost close to zero
(`compute-cost-model.md`). The open cost is the container registry, 0.1462 € a
day while it exists.

---

## Sources

- [AI-300 study guide](https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-300): read 2026-10-01 (last updated 2026-03-05); objectives
- [What is an Azure Machine Learning workspace?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace): read 2026-10-01 (ms.date 2026-02-10); §§ 1–2
- [Manage Azure Machine Learning workspaces by using Azure CLI](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-workspace-cli): read 2026-10-01 (ms.date 2025-06-13); §§ 2, 3, 5
- [Use an Azure Resource Manager template to create a workspace](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-workspace-template): read 2026-10-01 (ms.date 2025-12-22); § 4
- [Plan to manage costs for Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-plan-manage-cost): read 2026-10-01 (ms.date 2026-03-11); resources that bill after workspace deletion
- `infra/DEPLOY.md`, `README.md`: § 6
