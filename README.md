# AI-MLOps-GenAIOps

This is my hands-on preparation repository for **Microsoft AI-300 —
Operationalizing Machine Learning and Generative AI Solutions**. I use it to
build the exam topics as working artifacts instead of reading about them, so
everything here is something I can run, validate, and explain.

I develop it on a Pay-As-You-Go subscription with the spending limit off. My 
design decisions are actually protecting against what bills even if stopped. 
It means:

* cheapest viable SKU
* nothing left running
* as much validated locally as possible before anything touches Azure.

## How I work

I drive this repository spec-first, using [GitHub Spec Kit](https://github.com/github/spec-kit)
with Claude Code as the implementation tool.

For each unit of work I write a specification containing the objective, the
requirements, and **success criteria that a command can verify**. I review the 
diff and run the validation myself.

The rules I hold this repo to are written down in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md), and the most 
recurrent are:

- **Cost discipline**: every exercise declares whether it runs locally (free) or
  needs Azure, and anything that could add cost gets flagged with an estimate
  before it is built.
- **Validation before commit**: no IaC or CI change is proposed for commit until
  its validation step actually passes.

## What is built so far

### `infra/`: Azure baseline (Bicep)

A minimal but opinionated baseline: a Storage Account and a Key Vault.

- **Key Vault uses RBAC authorization**, not access policies: the access-policy
  model is legacy and does not compose with Azure's wider identity story.
- **The tenant ID is never hardcoded.** It comes from `subscription().tenantId`,
  so the template is portable across tenants.
- **Resource names are generated** with `uniqueString(resourceGroup().id)`,
  because storage account and vault names must be globally unique.
- **Soft delete, at first with 90-day retention and purge protection enabled**:
  purge protection is irreversible once on. The template no longer enables it, for
  reasons further down.
- **`Standard_LRS` and TLS 1.2 minimum**. The cheapest redundancy tier is the
  right default for learning; the TLS floor is not something to leave at default.

I then extended the baseline with an Azure ML workspace, plus the Application
Insights and Log Analytics resources it depends on.

- **No Container Registry, to begin with.** The workspace can provision one for
  itself, and it was not allowed: roughly $5/month for something not needed
  yet. That decision held until an exercise finally needed one, at which point
  the platform created it without asking. 
- **A system-assigned managed identity**. The Key Vault was already on RBAC,
  so granting roles to that identity is the natural next step.
- **Application Insights is workspace-based, so a Log Analytics workspace came
  with it.** Classic Application Insights is retired; a component without a
  backing workspace still compiles but is rejected on deployment. This is why
  the template has five resources and not the four first specified.
- **I did not take the newest API version for Log Analytics.** The provider
  offers `2026-03-01`, but no Bicep release has type definitions for it yet, so
  using it means `az bicep build` stops checking that resource's properties. 
  `2025-07-01` was taken instead: eight months older, fully type-checked. 

Everything above was validated locally with `az bicep build` before anything
touched Azure.

The compiled ARM JSON is **not** tracked. `main.bicep` is the primary source and
the JSON is a build artifact, so it lives in `.gitignore`.

---

### The first deployment

I have since deployed this template for real, into a throwaway resource group.
[`infra/DEPLOY.md`](infra/DEPLOY.md) is the runbook: It was written it before 
the deployment and revised immediately afterwards, so every expected value in 
it is now an observed one.

The deployment is what taught the difference it was until then only been 
asserting. Two defects were latent in a template that compiled without a single
warning and had passed CI:

- **The storage account name was one character over its limit.** `ai300storage`
  plus a 13-character `uniqueString()` is 25 characters, against a hard cap of
  24. Bicep does not validate name length at all.
- **`managedNetwork` was left to a service default I had never actually seen.**
  I assumed `what-if` would reveal it. It does not: `what-if` renders what the
  template declares, not what the resource provider applies at creation time.
  It was not just a theoretical issue: `AllowOnlyApprovedOutbound` provisions 
  a managed firewall billed hourly whether or not anything uses it. The template 
  now pins `Disabled` explicitly.

Two further things were decided by the subscription rather than by the template:
`westeurope` rejects every resource here with `RequestDisallowedByAzure`, a
capacity restriction Azure applies to new customers, which is why the default
region is now `northeurope`; and all five resource providers started out
unregistered, which fails a deployment immediately.

At rest this deployment should cost approximately nothing. I checked that in 
Cost Management, because a figure that is not near zero would mean something was 
provisioned that the template never declared. Confirmed at zero: only the
storage account and the vault have usage records at all, both at no charge.

The resource count, on the other hand, was wrong. My runbook said the group
should contain five resources; it contains six. Application Insights deployed a
notification group for itself ten minutes after the workspace. It costs nothing, 
but This same pattern subsequently compromised the identity construction 
discussed below: this platform provisions things the template never mentions.

The template compiles, and it also deploys. 

### The rise and fall of Workspace Identity

I restricted the managed identity to its required permissions. I did not succeed.
The attempt is kept in the repository.
The identity already held four role assignments no template had ever declared, 
including a wildcard permission across the whole resource group. Thus, the 
objective was never to provide a baseline, but to revoke what had been extended 
without request.

Two assumptions fell apart. 
1. Empty credentials doesn't mean the data stores don't use them, but only that
   the tool hides them.
2. Already-deployed template showed changes on a clean run.

The single best habit to keep is comparing everything to a reference point before 
believing the output.

Most important lesson: after the platform's grant was removed, it quietly recreated
it under a new name. When told to stop assigning resource-group level permissions, 
it satisfied the literal requirement by breaking a single broad grant into three 
specific ones. he check passed for that scenario simply because it scanned a word 
within the scope string, rather than evaluating the actual reach. 
Unfortunately, I cannot adjust these permissions myself, as their management is 
controlled by the platform.. Using a user-assigned identity might avoid this, and 
since the vault's 90-day rule forces a new resource group, I'll need to rebuild the 
workspace anyway.

The workspace now authenticates through its own identity instead of account keys.
The template still includes an unused role assignment for the Key Vault, named 
deterministically so redeployment is idempotent.

### Deployment from CI without a stored secret

I fulfilled the previous phase's commitment by asking the same question, but using 
my own identity instead of the platform's. CI now deploys `main.bicep` 
authenticating over OIDC. There is no password and no certificate in the repository.
The method was failing on purpose: I initialized the role using the eight operations 
recorded in the activity log, allowing the deployment to fail five times; each error 
message stated what was missing, and it was promptly added. 

Two valuable mistakes: one reintroduced an operation I had previously removed; the 
other was a successful deployment despite a failing test run. 

During deployment, the workflow executes four commands that are expected to fail. 
Initially, one of these commands slipped through without actually being tested due 
to a misleading exit code and error class. Later, verifying the grant proved tricky: 
simply withdrawing it triggered a local "no subscriptions found" error rather than 
an actual access denial. To achieve a true verification, I had to test the raw HTTP 
requests directly—confirming a 403 status without the grant and a 201 with it—thereby 
exposing a critical gap that the standard test suite would have missed.

### An input source and an execution target

This feature equipped the workspace with both data and compute: a blob container, a 
datastore that authenticates as the workspace instead of holding a key, a cluster 
that scales to zero when idle. All declared in the template, all shipped through CI and 
the approval gate.

This run named three missing permissions at once, because validation checks the whole 
template before submitting any of it, while the earlier failures had only ever surfaced 
singly, during execution.

New measurements refined my understanding, showing that an inactive cluster consumes no 
vCPU quota; quotas measure actual resource utilization rather than template limits; 
because quota and cost are separate metrics, tracking one will not accurately predict the 
other. I looked for the networking resources promised in the design notes, but they 
weren't there. The grant I got based on them was canceled, and yet everything still 
worked fine.

### A successful training run paired with an unresponsive deployment

A training job runs on the cluster, reads from the datastore, and MLflow tracks it without 
any configuration. The model comes back as a versioned artifact, and the batch deployment 
names that version explicitly. Its predictions matched what was computed locally on all 
five hundred cases.

However, the endpoint answers nothing. Five invocations resulted in five failures: four 
crashed during image construction prior to node allocation.

I had tried logging the model in MLflow format specifically so Azure ML would write the 
scoring script and environment. The environment it synthesises needs a package requiring 
pyarrow<4, MLflow 3 requires >=4, so no version satisfies both. Consequently, I ended up 
having to use a custom scoring script, even though the format was designed to spare me from 
it.

I anticipated that the endpoint's identity would require an authorization gran, but endpoint 
has no identity. Because the model resides on the compute node, the cluster's identity 
handles the read operations. The underlying mechanism was correct, but the executing actor 
was mistaken. Furthermore, building that custom environment forced Azure ML create a container 
registry on its own. I set the template to 'none' on purpose, but now every redeploy tries to 
remove a registry from Azure that cannot be removed. 
It gave the project its first cost that doesn't stop (the container registry).

The conclusion: The environment needs to be torn down and recreated.

### An environment I can afford to delete

`main.bicep` now declares the container registry the platform had been attaching on its own. 
The Key Vault's purge protection can't be disabled either, which is precisely why throwaway 
environments shouldn't have it. Fast vault purging via the current template enables multiple 
cycle runs..

When I finally ran the setup end-to-end, the complete round trip took about twelve and a half. 
The time gap was driven not by infrastructure resources, but by the CI permissions model: 
redeploying into a previously uncovered resource group triggered sequential approval prompts 
for every missing operation, requiring three separate approvals just for a single resource type.

### A comment that had been wrong for two features

Re-reading the work against the documentation instead of against memory turned up a line that 
had survived two features unchallenged: a comment claiming -1 meant zero failure tolerance, when 
-1 is in fact the most permissive default. I corrected it to 0, labeled it as unverified rather 
than confirmed, and let three more write-ups join it in docs/exam-notes/ (sweeps, online 
endpoints, monitoring). 

NOTE: monitoring has been completely removed, because, with no production traffic, it just 
benchmarked the training data against itself and reported no drift.

### `genaiops/`: a model, a versioned prompt, and a call 

The generative component begins here, deliberately kept lean: a single token-billed model, version-controlled prompts residing in Git rather than a cloud portal, and API calls fully 
recoverable after closing the originating terminal. Isolated within swedencentral with zero 
overlap with the northeurope backbone, the setup consists strictly of a Foundry account and a 
project, purposefully omitting a hub to bypass the complex storage-vault-registry dependency 
chain that previously broke the template.

The permissions were wrong in both directions. The Owner role handles every control-plane 
action while excluding data actions, allowing Log Analytics queries to succeed immediately 
while chat completions returned a 401 until a dedicated role was explicitly assigned. API 
access restrictions depend entirely on the specific denial behavior rather than the apparent 
scope of a role. To avoid granting excessive permissions, one data-plane access request was intentionally omitted: retrieving the project telemetry connection string would have required 
granting broad data-plane access for a single lookup, resulting in a custom role outliving the 
resource group, so the connection string was read directly from App Insights instead.

The worthwhile defect emerged in tracing, not permissions: the first version sent telemetry on exit, but short-running CLI commands exited too quickly to transmit the data. Choosing the model revealed that the catalog says what a region offers, and only the quota API says what can been actually deploy. Measuring the idle daily cost required leaving the resource group standing overnight, which posed no risk since no active compute was running. The result registered as zero, but in Cost Management an absent row represents missing data rather than a confirmed zero; confirming this required cross-referencing a second resource group known to be billing on the same day.

### `qa-observability/`: assessing the responses without the bias of judgment

The logical next step from a retrievable call shifts the focus: from *what the model outputted* to *if it was actually useful*. Evaluation execution proceeded smoothly with ground-truth scoring and strict quality thresholds, yielding eight key findings during development. While evaluation spans return an HTTP 200, they fail to populate Log Analytics; after systematically eliminating the client, SDK, sampling configuration, and all potential tables, service-side adaptive sampling remains the most probable unverified cause.

Two of the remaining verifications depend on the missing spans, so finishing them would have meant asserting something not actually observed.

### `rag-optimization/`. Four methods and their variance

The final section analyzes how retrieval quality varies according to query design, utilizing eighteen notes divided into 222 chunks, a single index and four search methods including keyword, vector, hybrid, and semantic ranking, alongside 378 manually assigned relevance labels. Total indexing costs amounted to 0.0146 euros, leveraging the Free tier of AI Search selected proactively during the design phase.

The documented ranking order held at the top but failed in the middle. Semantic ranking won, yet plain vector search outperformed hybrid search, meaning adding a keyword component made the overall ranking worse than using vector search alone. The key metric to retain is the **unpublished margin** of a **27 % gain over keyword and under 4 % over plain vector**. Additionally, instances where every method located the correct material without placing it in the top three highlight how isolated metrics create opposing conclusions, requiring both recall and ranking perspectives to capture the actual result.

This block was also the first built under a rule added to the constitution the same week: read the documentation into `docs/exam-notes/` **before** the plan freezes.

### `.github/workflows/` — validation and deployment

**`bicep-validate.yml`** — recompiles every template under `infra/` on every push
and pull request touching it. No Azure credentials, no deployment, no token
permissions beyond reading the repository. A fork's pull request runs it
unchanged.

**`infra-deploy.yml`** — deploys `main.bicep` on a merge to `main` or on manual
dispatch. Authenticates over OIDC against a federated credential bound to the
`azure-deploy` environment, so a run that has not passed the approval gate cannot
obtain a token. A second job runs the four boundary probes as assertions; a probe
that succeeds fails the run.

## Running the validation locally

```bash
az bicep install
for template in infra/*.bicep; do az bicep build --file "$template"; done
```

An exit code of 0 means the templates compile. This requires no Azure
subscription and costs nothing — it is the same check `bicep-validate.yml` runs.
