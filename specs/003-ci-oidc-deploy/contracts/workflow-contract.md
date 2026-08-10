# Contract: the workflows

**Feature**: `003-ci-oidc-deploy` · **Date**: 2026-08-09

Two workflows, kept separate on purpose. FR-015: a change to one must not be able
to hand the other access it did not have.

## `.github/workflows/bicep-validate.yml` — existing, minimally extended

| Property | Value |
| --- | --- |
| Triggers | `push` to `main` and `pull_request` to `main`, paths `infra/**` and the workflow file |
| Permissions | `contents: read` — unchanged |
| Credentials | none, and none obtainable |
| Change | build **every** `*.bicep` under `infra/`, not only `main.bicep` |

The only change is the build step's scope, so `infra/ci-identity.bicep` is
validated too (Principle V). No permission is added; no `id-token` is requested;
a fork pull request continues to run it exactly as today (FR-013).

Globbing the directory rather than naming files is deliberate: a template added
later is validated without anybody remembering to add it.

## `.github/workflows/infra-deploy.yml` — new

| Property | Value |
| --- | --- |
| Triggers | `push` to `main` limited to `infra/**`, **and** `workflow_dispatch` |
| Environment | `azure-deploy` |
| Permissions | `id-token: write`, `contents: read` — nothing else |
| Concurrency | group per workflow, `cancel-in-progress: false` |

**No `pull_request` trigger of any kind.** FR-014: a fork cannot cause either
event. `workflow_dispatch` requires write access to the repository (FR-014a).

Both triggers enter the `azure-deploy` environment, so both pass the gate. There
is no path into this workflow that skips it — and if there were, R3's subject
binding means the token exchange would fail anyway.

`cancel-in-progress: false` rather than `true`: cancelling a deployment mid-flight
could leave the environment partly applied, and during discovery a cancelled run
produces an error that looks like a refusal. Queueing is slower and honest.

### Job 1 — `deploy`

1. Check out the repository.
2. Authenticate with `azure/login`, OIDC, no secret. Client, tenant and
   subscription identifiers come from repository secrets (R10).
3. `az bicep install`.
4. `az deployment group create -g rg-ai300-test01 -f infra/main.bicep -n ai300-ci-<run_id>`.

Step 4 is a real deployment (FR-010). A uniquely named deployment per run makes
the history readable and gives SC-001 a record to point at.

### Job 2 — `boundary`

Runs after `deploy`, in the same environment, as the same principal. Executes the
four assertions in [boundary-probes.md](boundary-probes.md). A probe that
succeeds turns the run red.

Separating it from `deploy` keeps the distinction legible in the run history: a
red `deploy` means the role is too narrow, a red `boundary` means it is too wide.
That is the whole feature, visible in two job names.

## Actions, pinned

```yaml
uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
uses: azure/login@858f4093d287a904987dfd22abd163280f939550 # v3.0.1
```

Commit SHAs, not tags (R9). A tag can be repointed by whoever controls the
action, and this workflow holds an identity that can write to the subscription.
The readable tag stays in a trailing comment so the pin is auditable.

## What is stored in the repository

| Name | Kind | Is it a credential? |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | secret | no — an identifier |
| `AZURE_TENANT_ID` | secret | no — an identifier |
| `AZURE_SUBSCRIPTION_ID` | secret | no — an identifier |
| `AZURE_CLIENT_OBJECT_ID` | secret | no — an identifier |

`AZURE_CLIENT_OBJECT_ID` was added during implementation: probe P3 needs an
assignee object id, and the principal cannot read its own from the directory.

Nothing else. No password, no certificate, no connection string. SC-004's third
refusal proves that holding all three grants nothing.
