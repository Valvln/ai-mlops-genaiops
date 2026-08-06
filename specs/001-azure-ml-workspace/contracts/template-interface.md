# Template Interface Contract

**Feature**: [spec.md](../spec.md) | **Date**: 2026-08-06

`infra/main.bicep` is consumed by whoever deploys it and by any later template
or script that needs to address these resources. Its parameters and outputs are
therefore a public surface: changing them breaks callers. This file records that
surface before and after the feature.

## Parameters

| Name | Type | Default | Status |
| --- | --- | --- | --- |
| `location` | string | `'westeurope'` | existing — unchanged |
| `storageAccountName` | string | `'ai300storage${uniqueString(resourceGroup().id)}'` | existing — unchanged |
| `keyVaultName` | string | `'ai300kv${uniqueString(resourceGroup().id)}'` | existing — unchanged |
| `workspaceName` | string | `'ai300ml${uniqueString(resourceGroup().id)}'` | **new** (FR-002) |

All four parameters have defaults, so the template stays deployable with no
parameter file. The new parameter follows the naming and defaulting convention
of the two that precede it; a caller who was deploying the template before this
change keeps working with no edits.

The Log Analytics and Application Insights names are **not** parameters. They
are derived inline. If a later feature needs to control them, promoting them is
a backward-compatible change (adding a defaulted parameter); the reverse would
not be.

## Outputs

| Name | Type | Value | Status |
| --- | --- | --- | --- |
| `storageAccountName` | string | `storageAccount.name` | existing — unchanged |
| `keyVaultUri` | string | `kv.properties.vaultUri` | existing — unchanged |
| `workspaceName` | string | `mlWorkspace.name` | **new** (FR-010) |
| `workspaceId` | string | `mlWorkspace.id` | **new** (FR-010) |

Outputs are appended, never reordered or renamed. `workspaceId` is the full ARM
resource id, which is what `az ml` commands and downstream templates need;
`workspaceName` is the short form for CLI use with an explicit resource group.

## Compatibility statement

This feature is **purely additive** to the interface: one new parameter with a
default, two new outputs. No existing name, type, default, or value changes. Any
consumer of the template written before this feature continues to work
unchanged.

## Not part of the contract

The managed identity's principal id is deliberately **not** exposed as an
output. It would be useful for role assignments, but role assignments are a
separate future feature, and an output added speculatively is an interface
commitment made without a caller. It can be added when something needs it.
