# Quickstart: validating feature 003

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

How to check that the feature does what it claims. Read
[contracts/](contracts/) for what each object is; this file is about proving it
works.

Before anything:

```bash
export PATH="/usr/local/bin:$PATH"   # or az and gh appear uninstalled
az account show --query "{sub:id, tenant:tenantId}" -o tsv
```

## Cost

**Zero.** Every object created is control-plane metadata or a free-tier feature:
an application registration, a federated credential, a role definition, a role
assignment, two empty resource groups, and Actions minutes on a public
repository. The deployment redeploys the template already in place.

Should a probe unexpectedly succeed, what it creates — a resource group, a role
assignment, a user-assigned identity — is free as well. That was a selection
criterion, not luck (R7).

## Capture the baseline first

SC-002 compares against this, so take it before anything changes:

```bash
az resource list -g rg-ai300-test01 --query "sort_by([].{name:name,type:type,sku:sku.name}, &name)" \
  -o json > specs/003-ci-oidc-deploy/evidence/inventory-before.json
```

Expected: six resources (R1).

## Validating each criterion

### SC-001 — it really deployed

Green alone is not enough; the environment must show a deployment record.

```bash
gh run list --workflow infra-deploy.yml --limit 1
az deployment group list -g rg-ai300-test01 \
  --query "[?starts_with(name,'ai300-ci-')].{name:name,state:properties.provisioningState,ts:properties.timestamp}" \
  -o table
```

Passes when a record named for that run reports `Succeeded`. The history will
also hold failed records from discovery — expected, and explicitly not counted
against this criterion.

### SC-002 — nothing changed

```bash
az resource list -g rg-ai300-test01 --query "sort_by([].{name:name,type:type,sku:sku.name}, &name)" \
  -o json > specs/003-ci-oidc-deploy/evidence/inventory-after.json
diff specs/003-ci-oidc-deploy/evidence/inventory-before.json \
     specs/003-ci-oidc-deploy/evidence/inventory-after.json && echo "unchanged"
```

Passes on an empty diff.

### SC-003 — the boundary held

The four probes run inside the workflow, so this criterion is read from the run:

```bash
gh run view <run-id> --log --job boundary
```

Passes when all four refused with an authorization error. **A probe that
succeeded turns the job red** — the workflow asserts the refusals rather than
reporting them, so a widened boundary cannot pass unnoticed.

Check the failure mode too, not only the result: a probe that failed with
`MissingSubscriptionRegistration` or `ResourceGroupNotFound` is broken, not
passing (FR-017).

### SC-004 — the identity cannot be assumed

Three refusals, all at **authentication**. The first two are captured during
setup; the third can be run at any time:

```bash
az login --service-principal \
  --username "$AZURE_CLIENT_ID" \
  --tenant "$AZURE_TENANT_ID" \
  --federated-token "not-a-token"
```

Passes when it is refused. An *authorization* error anywhere here would mean the
context was trusted after all — that is a finding, not a pass.

### SC-005 — pull requests validate and do not deploy

```bash
gh pr checks <pr-number>
gh run list --workflow infra-deploy.yml --event pull_request   # must be empty
```

Passes when the validation workflow is green for the pull request and the
deploying workflow has no run for that event.

### SC-006 — no secret ever existed

```bash
az ad app credential list --id "$AZURE_CLIENT_ID" --query "length(@)"
az ad app credential list --id "$AZURE_CLIENT_ID" --cert --query "length(@)"
```

Both must return `0`. Meaningful only because SC-001 already passed: the
deployment demonstrably happened while this was true.

### SC-007 — nothing granted is inert

Two halves.

**The grant** — withdraw, run, restore, run:

```bash
az role assignment delete --assignee-object-id <sp-object-id> \
  --scope "/subscriptions/<sub>/resourceGroups/rg-ai300-test01"
gh workflow run infra-deploy.yml    # must fail; approve the gate, record the error
az deployment group create -g rg-ai300-test01 -f infra/ci-identity.bicep \
  --parameters principalId=<sp-object-id>
gh workflow run infra-deploy.yml    # must succeed
```

A deployment that still succeeds without the grant means something else is
authorizing it. That is exactly the defect feature 002 shipped, and it fails this
criterion.

**The operations** — every one in the final role traces to a line in
[contracts/role-definition.md](contracts/role-definition.md) with a non-empty
Provenance cell. Any operation without one is deleted, then the workflow is run
again to confirm the deployment still passes.

### SC-008 — cost

```bash
az consumption usage list --start-date 2026-08-09 --end-date <closing-date> \
  --query "[?pretaxCost!='0'].{meter:meterDetails.meterName, cost:pretaxCost}" -o table
```

Passes when no meter appears that was not already present, and the total
attributable to this feature is `0.00`.

### SC-009 — the reversal runs

Every step in the reversal is a command, and the count of removal commands
matches the count of objects created — seven, per
[data-model.md](data-model.md). The reversal is recorded in `infra/DEPLOY.md`
and is not executed as part of closing the feature; the environment is left
working.

## The two failure modes to expect, and not mistake for defects

**A red `deploy` job** means the role is missing an operation. The error names
it. That is FR-006a's verification pass working — add the operation with the run
id as its provenance and go again.

**A red `boundary` job** means a probe succeeded, so the authority is wider than
declared. That is a real defect and the feature is not done.

Both are normal during implementation. Only the second is a problem.
