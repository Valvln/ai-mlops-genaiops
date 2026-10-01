# Identity and access for Azure Machine Learning workspaces

**Status: built and measured, with one reduction that failed.** The workspace
uses a system-assigned identity. Feature 002 tried to cut that identity's
permissions and found that the platform recreates them. The compute cluster
has its own system-assigned identity with Storage Blob Data Reader on two
containers. The Foundry equivalent is `foundry-rbac-and-authentication.md`.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objective: *Configure identity and access
management for workspaces*.

---

## 1. Built-in roles on a workspace

| Role | What it allows |
| --- | --- |
| **AzureML Data Scientist** | every action in the workspace **except** creating or deleting compute and modifying the workspace itself |
| **AzureML Compute Operator** | create, manage, delete and access compute |
| **Reader** | read-only; can list and view assets, **including datastore credentials** |
| **Contributor** | view, create, edit, delete assets; create compute; submit runs; deploy |
| **Owner** | Contributor plus role assignments |
| **AzureML Registry User** (on a registry) | read, write and delete assets in a registry; can't create or delete the registry |

Learn's own combination: **AzureML Data Scientist + AzureML Compute Operator**
lets a user run experiments and create compute self-service.

Rules Learn states:

- **Scope is independent per level.** Owner on a workspace isn't Owner on its
  resource group.
- **Creating a resource doesn't make you its Owner.** You inherit your highest
  role at that scope.
- Use **Microsoft Entra security groups**: group owners manage membership
  without a role on the workspace, and groups avoid the subscription limit on
  role assignments.
- **Quota operations need subscription-scope permissions.**
- New role assignments can take **up to an hour** to apply over cached
  permissions. Custom role updates take 15 minutes to an hour.
- Creating a workspace for the first time may need
  `Microsoft.MachineLearningServices/register/action`.
- Attaching a user-assigned identity to compute needs
  `Microsoft.ManagedIdentity/userAssignedIdentities/assign/action` (the Managed
  Identity Operator role).

### Custom roles

Built from operations under `Microsoft.MachineLearningServices/workspaces/...`.
Some actions differ between v1 and v2 APIs: `jobs` (v2) against `experiments`
(v1), `components` against `modules`, `datasets/versions` against `datasets`.
Wildcards can cover both.

Two operations that come up in scenarios:

| Need | Operation |
| --- | --- |
| retrieve an online endpoint's key or token | `onlineEndpoints/listKeys/action`, `onlineEndpoints/token/action` |
| read credentials of a credential-based datastore | `datastores/listsecrets/action` |
| submit any v2 job | `jobs/*` plus environment build and read actions |

---

## 2. The workspace's managed identity

The workspace talks to its storage, Key Vault and container registry through a
managed identity, **system-assigned by default**. The identity has the same
name as the workspace.

| Identity type | Role assignment creation |
| --- | --- |
| System-assigned (SAI) | **managed by Microsoft** |
| System-assigned + user-assigned (SAI+UAI) | **managed by you** |

- You can move a workspace from SAI to SAI+UAI. **Not back.**
- Workspaces created after **2024-11-19** give the SAI the **Azure AI
  Administrator** role on the resource group. Earlier ones gave Contributor.
  `allowRoleAssignmentOnRG` (CLI `--allow-roleassignment-on-rg`) is the property
  Learn uses to convert an older workspace.
- **A user-assigned workspace identity needs these grants from you:**

| Resource | Role |
| --- | --- |
| workspace | Contributor |
| storage | **Contributor (control plane)** + **Storage Blob Data Contributor (data plane)**, the second for data preview in studio |
| Key Vault, RBAC model | **Contributor (control plane)** + **Key Vault Administrator (data plane)** |
| Key Vault, access-policy model | Contributor + any access policy except purge |
| Container Registry, Application Insights | Contributor |

Learn labels the planes itself in this table. **Contributor on storage manages
the account and doesn't read blob data.** Data needs a data-plane role.

### Data isolation for shared resources

`enableDataIsolation` prefixes container names, secret names and image names
with the workspace GUID, and adds an ABAC condition to the identity's storage
role. **Set only at creation.** Default: enabled for hub and project
workspaces, disabled for default workspaces.

---

## 3. Compute identities

- A compute **cluster** has **one** system-assigned identity **or** one or more
  user-assigned identities, **never both**.
- The cluster's default identity sets up storage mounts, pulls images and reads
  datastores. Code inside a job picks a specific identity by `client_id`, or by
  `DEFAULT_IDENTITY_CLIENT_ID`.
- A compute identity gets **AcrPull on the workspace registry automatically**.
  If the compute existed before the registry, assign AcrPull by hand.
- A **registry's** own ACR is never accessed by the workspace or compute
  identity: the registry issues a scoped ACR token for the pull.
- An **online endpoint's** identity is fixed at creation and can't change.
- A compute instance with a managed identity doesn't idle-shut-down unless the
  identity has Contributor on the workspace.

---

## 4. Which identity reads the data

| Context | Identity used |
| --- | --- |
| job, datastore **with** cached credentials | the stored credential |
| job, credential-less datastore, `identity: managed` | the **compute's** managed identity |
| job, credential-less datastore, `identity: user_identity` | the **submitting user** |
| job, no `identity` property, credential-less datastore | compute managed identity, as fallback |
| notebook, studio browse | user identity |
| studio data preview behind a VNet | workspace managed identity |

- User identity and compute identity **can't be mixed in one job**.
- **Pipelines:** set user identity on each step that runs on compute. Setting it
  at the root or on a pipeline component doesn't work for nested components.
- Studio doesn't support submitting with user identity; the CLI and SDK v2 do.
- Batch endpoints split the work between two identities: see
  `batch-endpoints.md` § 4.

### Credential-based against identity-based datastores

Credential-based datastores cache the key, SAS or service principal secret in
the workspace's Key Vault, and **other workspace users with enough permissions
can retrieve them**. Identity-based datastores keep nothing and leave access to
storage RBAC.

---

## 5. What this repository measured, and what it did not

**Measured** (`infra/DEPLOY.md` § 6, `specs/002-…`, `specs/004-…`,
`specs/005-…`):

- **The SAI held grants no template declared**, including a wildcard at
  resource-group scope. Deleting one caused the platform to recreate it within
  seconds under a new name. This is § 2's "managed by Microsoft", observed.
- **`allowRoleAssignmentOnRG: false` moved the authority.** The single Azure AI
  Administrator grant on the resource group disappeared and three appeared, one
  per dependent resource.
- **The open question in the tracker** (does the platform auto-grant to a
  user-assigned identity?) has a documented answer in § 2: with SAI+UAI, role
  assignment creation is **managed by you**. Not tested here.
- **The identity that performs the operation is the one that needs the grant.**
  The cluster identity reads training data (feature 004) and mounts the model
  for batch scoring (feature 005). The batch endpoint has no identity
  (`identity: null`).
- **Key Vault in RBAC mode.** The template sets `enableRbacAuthorization: true`
  and grants the workspace identity Key Vault Secrets User, a data-plane role.
  The platform added Key Vault Administrator on its own.

**Not measured:** a user-assigned workspace identity, data isolation, user
identity jobs, a custom role for data scientists.

---

## 6. What this note would cost to verify

A user-assigned identity test needs a fresh workspace, because SAI+UAI can't go
back to SAI. On a throwaway resource group that is one deployment and one
teardown: about 0.15 € for the registry day, nothing else at rest.

---

## Sources

- [Manage access to Azure Machine Learning workspaces](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles): read 2026-10-01 (ms.date 2026-01-08); § 1, Azure AI Administrator
- [Set up authentication between Azure Machine Learning and other services](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-identity-based-service-authentication): read 2026-10-01 (ms.date 2026-01-22); §§ 2–4
- [Data administration](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-administrate-data-authentication): read 2026-10-01 (ms.date 2024-09-06); § 4
- [Create an Azure Machine Learning compute instance](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-compute-instance): read 2026-10-01 (ms.date 2025-08-13); idle shutdown with a managed identity
- [Share models, components, and environments across workspaces with registries](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-share-models-pipelines-across-workspaces-with-registries): read 2026-10-01 (ms.date 2026-02-11); registry ACR token
- `infra/DEPLOY.md` § 6, `specs/002-workspace-identity-least-privilege/`, `specs/005-training-job-batch-endpoint/results.md`: § 5
