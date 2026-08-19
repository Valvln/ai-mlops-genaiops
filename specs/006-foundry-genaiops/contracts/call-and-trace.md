# Contract: a call, its prompt version, and its trace

What `call_model.py` and `query_trace.py` must guarantee between them, so User
Stories 2 and 3 are provable rather than asserted.

## `call_model.py`

**Input**: a path to a `.prompty` file under `genaiops/foundry-block3/prompts/`.

**Must do, in order**:

1. Read the prompt file from disk — never accept prompt text typed inline or
   pasted from the Foundry portal (FR-006's whole point is that the file is
   the source of truth).
2. Resolve the prompt file's current git identity (e.g. `git log -1
   --format=%H -- <file>`) and attach it as a span attribute
   (`prompt.version` or equivalent) **before** the call is sent — the version
   being traced is the version that was actually used, not the working tree's
   current state at query time, which may have moved on.
3. Send exactly one completion request to the `gpt-4.1-mini` deployment via
   the OpenAI-compatible endpoint, authenticated with Entra ID
   (`azure-identity`), instrumented so the request emits an OpenTelemetry
   span exported to the connected Application Insights resource.
4. Print (for the operator's immediate feedback only, never as the record of
   truth) the response and the span/trace id.

**Must NOT do**: retry silently on failure, or swallow an authentication or
quota error — a refusal here is exactly the kind of error this project reads
rather than works around (`infra/DEPLOY.md`'s "Reading a red run correctly").

## `query_trace.py`

**Input**: a trace or span id (or a narrow time range) — never the same
process's in-memory state from `call_model.py`. Run as a **separate
invocation**, ideally after closing the terminal that ran `call_model.py`, so
retrieval is proven rather than assumed (this is what makes SC-004 a real
test and not a restatement of "the call happened").

**Must do**:

1. Query the Log Analytics workspace connected to the Foundry project (KQL
   over the `AppTraces`/`AppDependencies` tables, or the SDK equivalent) for
   the given trace id.
2. Print, from the retrieved record and nothing held in memory from the call:
   the prompt version attribute, the deployment name, and the response
   content.

**Requires**: the querying identity holds `Log Analytics Reader` on the
Application Insights resource (and `Privileged Monitoring Data Reader` if the
underlying tables are protected) — per
[Set Up Tracing for AI Agents in Microsoft Foundry][trace], this is not
implied by Owner/Contributor on the resource group and may need an explicit
role assignment during implementation.

## Acceptance mapping

| Scenario | Script(s) | Proves |
| --- | --- | --- |
| User Story 1, Scenario 2 (a call returns a response) | `call_model.py` alone | SC-002 |
| User Story 2, Scenario 1–2 (prompt is a versioned file) | `call_model.py` reading the file + `git log --follow` on it | SC-003 |
| User Story 3, Scenario 1 (retrieve after the fact) | `call_model.py` then, in a separate session, `query_trace.py` | SC-004 |
| User Story 3, Scenario 2 (two calls, two prompt versions, distinguishable) | `call_model.py` run twice against two prompt file revisions, then `query_trace.py` against both trace ids | SC-004, extended |

[trace]: https://learn.microsoft.com/en-us/azure/ai-foundry/observability/how-to/trace-agent-setup
