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

---

## No credential ever existed

**Before** — 2026-08-09T07:35:57Z, immediately after registration:

```console
$ az ad app credential list --id <client-id> --query 'length(@)' -o tsv
0
$ az ad app credential list --id <client-id> --cert --query 'length(@)' -o tsv
0
```

*After* half pending — it is taken once a deployment has demonstrably succeeded,
because that is what makes it mean anything (SC-006).

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

Pending — T017.

## Four authorization refusals

Pending — T022.

## Three authentication refusals

Pending — T025.

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

Pending — T016.

## Nothing granted is inert

Pending — T035.

## Cost

Pending — T039.
