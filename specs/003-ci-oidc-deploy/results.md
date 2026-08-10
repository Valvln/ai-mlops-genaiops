# Results: what was observed

**Feature**: `003-ci-oidc-deploy` · **Started**: 2026-08-09 · **Status**: in progress

The closing record. Every success criterion in [spec.md](spec.md) is settled from
this file, and every entry here is something that was *run* — a command and what
it returned. Nothing is settled by reading a configuration and forming a
judgement, which is the failure this feature was written against.

**Identifiers are elided** the way [research.md](research.md) elides them —
`5900fbc9-…`. `origin` is public, and R10's reasoning about not publishing tenant
and subscription identifiers applies to a tracked record as much as to repository
variables. Everything else is verbatim. The unredacted captures live in
`evidence/`, which is gitignored.

---

## The gate and what is stored

**Environment `azure-deploy`**, created 2026-08-09:

```json
{
  "name": "azure-deploy",
  "rules": [
    {"type": "required_reviewers", "prevent_self_review": false, "reviewers": ["Valvln"]},
    {"type": "branch_policy"}
  ],
  "branch_policy": {"custom_branch_policies": true, "protected_branches": false}
}
```

Deployment branch policies: `main` only.

`prevent_self_review` is **false**, deliberately. There is one author; enabling it
would make every deployment permanently unapprovable. The gate is a deliberate
pause, not a separation of duties, and this setting is where that distinction
stops being a claim and becomes visible (R5).

**Stored in the repository** — four values, none of them a credential:

| Name | What it is |
| --- | --- |
| `AZURE_CLIENT_ID` | which application |
| `AZURE_TENANT_ID` | which directory |
| `AZURE_SUBSCRIPTION_ID` | which subscription |
| `AZURE_CLIENT_OBJECT_ID` | which principal, for probe P3's assignee |

The fourth is a **deviation from the plan**, which named three. Probe P3 attempts
a role assignment and needs an assignee object id; the principal cannot look its
own up, because it holds no directory permission. Hardcoding it in the workflow
would publish a directory object id on a public repository for no gain, so it is
stored the same way as the other three. It confers nothing on its own — which is
the claim SC-004's third refusal exists to test, and it now covers four values
rather than three.

No password, no certificate, no connection string.

### R10's reasoning was partly wrong, and the decision survives it

R10 chose secrets over repository variables partly on this ground: storing them
as variables *"publishes a tenant and subscription identifier on a public
repository for no gain"*.

The subscription identifier was already published. `infra/DEPLOY.md` has carried
it in plain text since feature 001, and `specs/002-…/research.md` carries the
workspace identity's object id:

```console
$ git grep -noE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" -- '*.md'
infra/DEPLOY.md:7:5900fbc9-…
specs/003-ci-oidc-deploy/research.md:91:85e8321f-…
```

So the avoided harm was already incurred, and the argument for secrets was
carrying weight it did not have.

The decision still stands, on the reason that always did the real work: these
values are **not credentials**, so FR-001 is indifferent to which box they sit
in, and secrets are the conventional home at no cost. What changes is only the
justification — and it is recorded here rather than quietly corrected, because a
feature that spent five runs refusing to accept plausible reasoning in place of
observation should hold its own reasoning to the same standard.

Whether `DEPLOY.md` should be redacted is a separate decision, and the author's:
a subscription id is not a credential either, and nothing here depends on it
being secret.

---

## No credential ever existed

**Before** — 2026-08-09T07:35:57Z, immediately after registration:

```console
$ az ad app credential list --id <client-id> --query 'length(@)' -o tsv
0
$ az ad app credential list --id <client-id> --cert --query 'length(@)' -o tsv
0
```

**After** — 2026-08-10T08:40:54Z, once the deployment had demonstrably
succeeded:

```console
$ az ad app credential list --id <client-id> --query 'length(@)' -o tsv
0
$ az ad app credential list --id <client-id> --cert --query 'length(@)' -o tsv
0
$ az ad app federated-credential list --id <client-id> --query 'length(@)' -o tsv
1
```

Zero passwords, zero certificates, one federated credential — which is not a
secret but a trust condition: it holds no material an attacker could copy, only
a statement about which runs may present a token.

The ordering is what makes this mean anything. SC-001 passed first, so the
deployment demonstrably happened while no secret existed. Enumerating an empty
credential list on an identity that had never deployed would prove nothing at
all.

---

## The authority granted

Deployment `ai300-ci-identity-001`, run by the author, `Succeeded`.

```console
$ az role definition list --custom-role-only true \
    --query "[].{name:roleName,type:roleType,scopes:assignableScopes,actions:permissions[0].actions}"
```

```json
[{
  "name": "AI300 CI Deployer (rg-ai300-test01)",
  "type": "CustomRole",
  "scopes": ["/subscriptions/5900fbc9-…/resourceGroups/rg-ai300-test01"],
  "actions": [
    "Microsoft.Resources/deployments/write",
    "Microsoft.Resources/deployments/operationStatuses/read",
    "Microsoft.Storage/storageAccounts/write",
    "Microsoft.KeyVault/vaults/write",
    "Microsoft.OperationalInsights/workspaces/write",
    "Microsoft.Insights/components/write",
    "Microsoft.MachineLearningServices/workspaces/write",
    "Microsoft.Authorization/roleAssignments/write"
  ]
}]
```

```console
$ az role assignment list --assignee <sp-object-id> --all \
    --query "[].{role:roleDefinitionName,scope:scope}"
[{"role": "AI300 CI Deployer (rg-ai300-test01)",
  "scope": "/subscriptions/5900fbc9-…/resourcegroups/rg-ai300-test01"}]
```

One assignment, one scope. `assignableScopes` holds that same single resource
group, so the role cannot be assigned elsewhere even by an Owner who tried — a
second, independent bound on FR-005.

These eight are the **derivation pass only**, and the set is known-incomplete on
purpose: the activity log records writes and actions, not most reads. What it
missed is expected to surface as a deployment failure naming the operation.

---

## The observed subject

Run `31302527002`, workflow `oidc-claims-probe.yml`, dispatched on `main`. Two
jobs, two contexts, and the difference between them is the trust condition.

**Gated** — the job that entered the `azure-deploy` environment:

```text
sub: repo:Valvln@188171957/ai-mlops-genaiops@1324268843:environment:azure-deploy
aud: api://AzureADTokenExchange
iss: https://token.actions.githubusercontent.com
```

**Ungated** — same repository, same branch, same run, no environment:

```text
sub: repo:Valvln@188171957/ai-mlops-genaiops@1324268843:ref:refs/heads/main
aud: api://AzureADTokenExchange
iss: https://token.actions.githubusercontent.com
```

Two things are settled here.

**The immutable format is real, not merely documented.** Both subjects carry
numeric owner and repository ids. R3 predicted this from the repository's
creation date — 2026-08-05, three weeks after GitHub's cutover — and the
prediction held. Writing `repo:Valvln/ai-mlops-genaiops:environment:azure-deploy`
would have produced a credential that never matched, failing as
`AADSTS70021: No matching federated identity record found` — an error that reads
like a typo in the environment name and gets debugged in the wrong place.

**The environment is what the token names.** The gated and ungated subjects
differ in their last segment and nowhere else. Binding the federated credential
to `:environment:azure-deploy` therefore binds it to the gate, not to the branch:
a run that has not entered the environment carries a subject the credential
cannot match. The gate is enforced by Entra, not only by GitHub.

Both jobs failed to authenticate, with the same error:

```text
AADSTS70025: The client '***'(ai300-github-deploy) has no configured federated
identity credentials.
```

That is the **weak** form of SC-004's first refusal — it proves only that nothing
was configured yet. The sharp form is captured in *Three authentication refusals*
below, once the credential exists and the ungated job must still be refused.

The federated credential was then created from the observed gated subject:

| Field | Value |
| --- | --- |
| Name | `github-azure-deploy-environment` |
| Issuer | `https://token.actions.githubusercontent.com` |
| Subject | `repo:Valvln@188171957/ai-mlops-genaiops@1324268843:environment:azure-deploy` |
| Audience | `api://AzureADTokenExchange` |

```console
$ az ad app federated-credential list --id <client-id> --query 'length(@)' -o tsv
1
$ az ad app credential list --id <client-id> --query 'length(@)' -o tsv
0
$ az ad app credential list --id <client-id> --cert --query 'length(@)' -o tsv
0
```

One way in, and it is not a secret.

## It really deployed

Run `31304591605`, triggered by a push to `main`, both jobs green.

```console
$ az deployment group show -g rg-ai300-test01 -n ai300-ci-31304591605 \
    --query "{name:name,state:properties.provisioningState,ts:properties.timestamp}"
{
  "name": "ai300-ci-31304591605",
  "state": "Succeeded",
  "ts": "2026-08-09T08:55:17.851585+00:00"
}
```

A record named for that run, created during it, `Succeeded`. Not a what-if, not
a validation. The history also holds `Failed` records from discovery; SC-001
asks for one succeeded record from the final run, and they do not count against
it.

**The inventory is unchanged** (SC-002):

```console
$ diff evidence/inventory-before.json evidence/inventory-after.json && echo "unchanged"
unchanged
```

Six resources before, six after, same names, same tiers.

**Repeating it succeeds** (FR-012): runs `31304052843` and `31304591605` both
deployed `main.bicep` unchanged, both succeeded, and the inventory diff above
was taken after the second.

### Closing state, after everything

Run `31374711441`, on `main` with the feature fully merged and both temporary
probe workflows deleted. Both jobs green.

```console
$ az deployment group show -g rg-ai300-test01 -n ai300-ci-31374711441
{"name": "ai300-ci-31374711441", "state": "Succeeded", "ts": "2026-08-10T09:34:32Z"}

$ diff evidence/inventory-before.json evidence/inventory-final.json && echo unchanged
unchanged

P1: refused on Microsoft.Resources/subscriptions/resourcegroups/write
P2: refused on Microsoft.Resources/subscriptions/resourcegroups/read
P3: refused on Microsoft.Authorization/roleAssignments/write
P4: refused on Microsoft.ManagedIdentity/userAssignedIdentities/write
```

Six resources at the start of the feature, six at the end, and the four
refusals still land on the four axes they claim. This run came after the grant
had been withdrawn and restored twice, which is the point of running it: the
environment is left working, and verified so rather than assumed so.

**Nothing the probes attempted exists:**

```console
$ az resource list -g rg-ai300-probe --query "length(@)" -o tsv
0
$ az group show -n rg-ai300-denied-probe
Message: Resource group 'rg-ai300-denied-probe' could not be found.
```

## Four authorization refusals

Run `31304591605`, job `The four refusals`, executed **as the deployment
identity** inside the workflow. Each is an assertion, not a capture: a probe that
succeeds turns the run red, so the boundary is checked on every deployment rather
than on the day it was built.

### Outside the scope

**P1 — write at subscription scope**

```console
$ az group create --name rg-ai300-denied-probe --location northeurope
ERROR: (AuthorizationFailed) The client '***' with object id '***' does not have
authorization to perform action 'Microsoft.Resources/subscriptions/resourcegroups/write'
over scope '/subscriptions/***/resourcegroups/rg-ai300-denied-probe'
```

**P2 — a named container other than the declared one**

```console
$ az group show --name rg-ai300-probe
ERROR: (AuthorizationFailed) … does not have authorization to perform action
'Microsoft.Resources/subscriptions/resourcegroups/read'
over scope '/subscriptions/***/resourcegroups/rg-ai300-probe'
```

`rg-ai300-probe` exists and is empty. That is FR-017b: against a resource group
that does not exist, a refusal cannot be told apart from an absence. A listing
was deliberately not used — the platform filters enumerations by permission, so
`az group list` would return an empty set with exit code zero, which FR-017a
rules out as evidence and which is the vacuity that let 002's SC-003 pass.

**P3 — granting authority outside the scope**

```console
$ az role assignment create --role Reader --assignee-object-id *** \
    --assignee-principal-type ServicePrincipal --scope /subscriptions/***
ERROR: (AuthorizationFailed) … does not have authorization to perform action
'Microsoft.Authorization/roleAssignments/write'
over scope '/subscriptions/***/providers/Microsoft.Authorization/roleAssignments/f2f54b8b-…'
```

The sharpest of the four. The principal **does** hold
`Microsoft.Authorization/roleAssignments/write` — `main.bicep` declares a role
assignment and cannot deploy without it. This proves the scope bounds it. A
principal that could assign roles at subscription scope could make itself Owner.

### Inside the scope, outside the authority

**P4 — an undeclared resource type, in the container the identity is scoped to**

```console
$ az rest --method put --url "https://management.azure.com/subscriptions/***/resourceGroups/rg-ai300-test01/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-ai300-denied-probe?api-version=2024-11-30" --body '{"location":"northeurope"}'
ERROR: (AuthorizationFailed) … does not have authorization to perform action
'Microsoft.ManagedIdentity/userAssignedIdentities/write'
over scope '/subscriptions/***/resourceGroups/rg-ai300-test01/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-ai300-denied-probe'
```

This is the axis a built-in general-management role would have left wide open,
and it is what the FR-006 clarification bought. Right resource group, right
subscription, and refused anyway.

### The probe that passed without testing anything

In the previous run, `31304052843`, all four probes reported as refused and the
job was green. P4's refusal named
`Microsoft.Resources/subscriptions/resourcegroups/read` — `az identity create`
reads the resource group before creating anything, that read was itself refused,
and the command never reached the resource type P4 exists to be refused on.

The refusal was genuine. The error class was right. The exit code was right. And
the axis SC-003 needs was **untested, and scored as tested** — on the same axis
P2 already covers.

That is feature 002's SC-003 failure reproduced inside this feature's own
assertion, which is worth stating plainly rather than quietly fixing: writing a
criterion that cannot be satisfied vacuously is harder than it looks, and being
alert to the failure mode was not sufficient to avoid it. What caught it was
reading the captured error instead of the pass/fail summary.

Two fixes, one per way in:

- the assertion now requires the refusal to **name the action the probe claims
  to test**, not merely to be an authorization error;
- P4 issues a single `az rest` request, so exactly one authorization decision is
  made and there is no preliminary call to fail on.

Both are in `.github/workflows/infra-deploy.yml`, and both are standing checks —
the run above is the first one they governed.

## Three authentication refusals

All three fail at **authentication**, before any authorization decision is
reached. An authorization error anywhere here would mean the context was trusted
after all — a finding, not a pass.

### A1 — this repository, the deploying branch, gate not passed

Run `31304840300`, dispatched on `main`, job `Claims from an ungated context` —
no `environment:`, therefore no gate.

```text
sub: repo:Valvln@188171957/ai-mlops-genaiops@1324268843:ref:refs/heads/main

AADSTS700213: No matching federated identity record found for presented
assertion subject 'repo:Valvln@188171957/ai-mlops-genaiops@1324268843:ref:refs/heads/main'
```

Everything about this run is legitimate except the gate. Same repository, same
branch, same workflow, same secrets — and refused, because the subject a token
carries outside the environment is not the subject the credential trusts.

This is the sharp form. The same job was run earlier, at `31302527002`, before
any federated credential existed, and failed with `AADSTS70025: has no
configured federated identity credentials`. That earlier failure proves only that
nothing was configured yet, and is recorded here as the weak version it is.

### A2 — a context that does not satisfy the trust condition at all

Run `31304841226`, same workflow dispatched on the feature branch:

```text
sub: repo:Valvln@188171957/ai-mlops-genaiops@1324268843:ref:refs/heads/003-ci-oidc-deploy

AADSTS700213: No matching federated identity record found for presented
assertion subject 'repo:Valvln@188171957/ai-mlops-genaiops@1324268843:ref:refs/heads/003-ci-oidc-deploy'
```

### A3 — the author's own machine, holding only what the repository stores

```console
$ az login --service-principal --username <client-id> --tenant <tenant-id> \
    --federated-token 'not-a-token'
ERROR: AADSTS50027: JWT token is invalid or malformed.
exit=1
```

**What this does and does not prove.** It shows that possessing the client id,
the tenant id and the subscription id gets you to the point of needing a token
from the trusted issuer, and no further — there is no credential to present, so
nothing can be replayed. It does not, by itself, distinguish "your token is
untrusted" from "your token is malformed"; a well-formed token from an untrusted
issuer would fail as A1 and A2 did, with `AADSTS700213`. Read together, the three
cover both.

### One correction to R3

R3 predicted the failure code `AADSTS70021`. The code actually returned is
`AADSTS700213`, with the subject quoted back in the message — which is more
useful than predicted, since it makes a subject mismatch self-diagnosing rather
than something to be debugged in the wrong place.

## Pull requests validate, and do not deploy

Pull request **#6**, which modified `infra/ci-identity.bicep`,
`.github/workflows/infra-deploy.yml`, `.github/workflows/bicep-validate.yml` and
`.gitignore`.

**The validation ran and passed**, run `31303183703`:

```console
$ gh pr checks 6
az bicep build   pass   26s
```

Its build step now covers every template, which is the point of the widening:

```text
--- infra/ci-identity.bicep
--- infra/main.bicep
2 template(s) built.
```

**It held no ability to authenticate.** The run's own record of what its token
was granted:

```text
##[group]GITHUB_TOKEN Permissions
Contents: read
Metadata: read
##[endgroup]
```

No `id-token`. Without it the OIDC token cannot be requested at all, so the
question of whether the subject would have matched never arises — the refusal
happens one layer earlier than the trust condition.

**The deploying workflow did not run**, and has never run for this event:

```console
$ gh run list --workflow infra-deploy.yml --event pull_request --json databaseId --jq 'length'
0
```

### The limit of this evidence, stated rather than left implicit

This pull request came from a branch in this repository, not from a fork. No
second account was stood up to author a genuine fork pull request, so SC-005 is
settled by what the repository observably ran plus the three independent
barriers R6 documents — the deploying workflow subscribes to no `pull_request`
event; a fork run cannot be granted `id-token: write`; and a fork subject would
name a `pull_request` context rather than `environment:azure-deploy`, which the
credential above cannot match.

Three barriers, each sufficient alone. But the criterion was verified against
the first two by observation and the third by reasoning, and that is weaker than
a fork actually trying. The checklist records this; it belongs with the evidence
too.

## Discovery

Five iterations. The role shipped with the eight operations derived from the
activity log and ended with thirteen. Every addition was named by a failure;
none was added because it seemed likely.

| Run | Named by the failure |
| --- | --- |
| `31303220508` | `Microsoft.Resources/deployments/validate/action` |
| `31303489048` | `Microsoft.KeyVault/vaults/read`, `Microsoft.OperationalInsights/workspaces/read` |
| `31303655969` | `Microsoft.MachineLearningServices/workspaces/read` |
| `31303842799` | `Microsoft.Resources/deployments/read` |
| `31304052843` | — green |

Full provenance per operation, with error excerpts, in
[contracts/role-definition.md](contracts/role-definition.md).

### The first failure was caused by the derivation pass, not missed by it

`validate/action` appears in the activity log. R2 **removed** it, reasoning that
it was there only because the author had run a preview by hand and that the
workflow performs no preview. The premise was true. The conclusion was wrong:
`az deployment group create` invokes `validate/action` itself before submitting.

FR-006a forbids taking operations from documentation because predicting what a
deployment needs is unreliable. That prohibition was honoured — and then the same
unreliable prediction was made in the opposite direction, to *subtract* an
operation the log had actually recorded. Deriving is safe because it observes;
subtracting from a derivation is a deduction wearing a derivation's clothes.

### A deployment that succeeded while its run went red

Run `31303842799` failed on `Microsoft.Resources/deployments/read` — and its
deployment record reads `Succeeded`:

```console
$ az deployment group list -g rg-ai300-test01 --query "[?starts_with(name,'ai300-ci-3')]" -o table
Name                  State      Ts
ai300-ci-31303842799  Succeeded  2026-08-09T08:35:47+00:00
```

The template deployed; the CLI then could not read back what it had just
created. SC-001 insists on the deployment record because green does not prove
something was deployed. This is the same coin's other face: **red does not prove
nothing was**. Both had to be checked against the history rather than inferred
from the run's colour.

### Two predictions that never materialised

R2 predicted reads on each declared resource type. Reads on
`Microsoft.Storage/storageAccounts` and `Microsoft.Insights/components` never
surfaced across five runs, and are **not** in the role. A prediction that does
not materialise is wrong, not pending.

## Nothing granted is inert

Two levels, per FR-008.

### The operations

Thirteen in the final role, thirteen accounted for. Zero survive unaccounted.

| # | Operation | Accounted for by |
| --- | --- | --- |
| 1 | `Microsoft.Resources/deployments/write` | derivation, activity log |
| 2 | `Microsoft.Resources/deployments/operationStatuses/read` | derivation, activity log |
| 3 | `Microsoft.Storage/storageAccounts/write` | derivation, activity log |
| 4 | `Microsoft.KeyVault/vaults/write` | derivation, activity log |
| 5 | `Microsoft.OperationalInsights/workspaces/write` | derivation, activity log |
| 6 | `Microsoft.Insights/components/write` | derivation, activity log |
| 7 | `Microsoft.MachineLearningServices/workspaces/write` | derivation, activity log |
| 8 | `Microsoft.Authorization/roleAssignments/write` | derivation, activity log |
| 9 | `Microsoft.Resources/deployments/validate/action` | run `31303220508` |
| 10 | `Microsoft.KeyVault/vaults/read` | run `31303489048` |
| 11 | `Microsoft.OperationalInsights/workspaces/read` | run `31303489048` |
| 12 | `Microsoft.MachineLearningServices/workspaces/read` | run `31303655969` |
| 13 | `Microsoft.Resources/deployments/read` | run `31303842799` |

Nothing was deleted, because nothing lacked provenance.

**The two halves are not equally strong, and the table should not hide it.**
Rows 9–13 are proven necessary: a deployment failed without each of them, and
the failure named it. Rows 1–8 rest on the activity log — evidence that the
operation *was invoked*, which is weaker than evidence that the deployment
*cannot proceed without it*. The clarification recorded in the spec accepted
that trade deliberately, on the grounds that a withdrawal cycle per operation
costs a gated run each and demonstrates what discovery already showed. It is a
reasoned trade, not an equivalence.

### The grant

Withdrawn, exercised, restored, exercised again. Same request both times, from
the same principal, through the same gate.

**Withdrawn** — run `31370325937`:

```console
PUT https://management.azure.com/subscriptions/***/resourcegroups/rg-ai300-test01/providers/Microsoft.Resources/deployments/ai300-necessity-31370325937?api-version=2026-06-01

{"error":{"code":"AuthorizationFailed","message":"The client '***' with object id
'…' does not have authorization to perform action
'Microsoft.Resources/deployments/write' over scope
'/subscriptions/***/resourcegroups/rg-ai300-test01/providers/Microsoft.Resources/deployments/ai300-necessity-31370325937'"}}
HTTP 403
```

**Restored** — run `31370554784`, byte-identical request:

```console
{"id":"/subscriptions/***/resourceGroups/rg-ai300-test01/providers/Microsoft.Resources/deployments/ai300-necessity-31370554784",
 "name":"ai300-necessity-31370554784","type":"Microsoft.Resources/deployments",
 "properties":{"mode":"Incremental","provisioningState":"…
HTTP 201
```

403 without the grant, 201 with it, nothing else changed. The grant is what
authorizes the deployment — not a broader permission sitting behind it, which is
precisely what feature 002 discovered it had been relying on.

The probe's template declares no resources, so the 201 created a deployment
record and nothing else. The inventory diff after all of this is still empty.

### Getting this evidence took three attempts, and the failures are the point

The first attempt withdrew the grant and re-ran the deploy workflow. It failed —
at `azure/login`, with `No subscriptions found`. A principal holding no role
assignment cannot see the subscription, so the run died on an **empty
enumeration**.

That would have satisfied SC-007's wording. It should not have satisfied
anybody: FR-017a exists because an empty result is indistinguishable from an
empty scope, and accepting one here would have settled the criterion that
separates this feature from 002 using the exact form of evidence that let 002's
SC-003 pass. The deployment failing is not in question — what was missing is any
demonstration that it failed *because permission was refused*.

The second attempt added `allow-no-subscriptions` so login would survive, and
still passed `subscription-id`; the action then ran `az account set` against a
subscription the principal could not enumerate, and login died on the local
account cache. The third dropped `subscription-id` and used `az rest`, which
resolves the subscription from that same cache before sending anything, and
failed with `Subscription not found` — the request never left the runner.

Three failures, one shape: **the tooling kept answering a local question before
the remote one could be asked.** Every convenience layer resolves state on the
client, and every such resolution is another way to fail without ever reaching
an authorization decision. The request finally went out as raw HTTP with a token
and a URL, because that is the only form with no local state to fail on.

Worth keeping, because the same trap took a different disguise in probe P4,
where `az identity create` read the resource group first and the refusal that
came back belonged to a boundary nobody was testing.

## Cost

Two windows compared, because SC-008 asks for **no meter that was not already
present** — a total alone would not settle that.

| Service | 2026-08-07 → 08-08, before | 2026-08-08 → 08-10, during |
| --- | --- | --- |
| Storage | 0.00047445 | 0.00048324 |
| Key Vault | 0.00003163 | 0.00001054 |
| Bandwidth | 0.00000009 | 0.00000011 |
| **Total** | **0.00050617 EUR** | **0.00049389 EUR** |

The same three services appear in both, and both totals round to **0.00 EUR**.
No meter appeared that was not already there, and the cost during the feature is
marginally *lower* than before it — these are the pre-existing resources from
feature 001 ticking over, not anything 003 introduced.

That is the expected result rather than a lucky one. Everything this feature
created is control-plane metadata or a free-tier feature: an application
registration, a federated credential, a role definition, a role assignment, an
empty resource group, GitHub environments and Actions minutes on a public
repository. The probes were chosen so that even an unexpected *success* would
create nothing billable (R7), and none of them succeeded.

### A note on how this was measured

`az consumption usage list` returned 12 usage records for the window with
`pretaxCost: None` and no meter names — on this subscription it reports usage
without cost. The figures above come from the Cost Management query API instead:

```console
$ az rest --method post \
    --url "https://management.azure.com/subscriptions/5900fbc9-…/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
    --body @query.json
```

Worth recording because quickstart.md names the `az consumption` command, and
following it would produce a table of nulls that could be misread as zero. Nulls
are an absence of data; zero is a measurement. The two must not be confused —
which is the same distinction this feature spent three attempts on elsewhere.
