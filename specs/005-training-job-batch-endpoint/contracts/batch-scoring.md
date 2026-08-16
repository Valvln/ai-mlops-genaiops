# Contract: registration and batch scoring

**Feature**: 005 · Phase 2

---

## 1. Registration

The model is registered from the **completed run**, not from a local file. That
is what carries the run reference into the registry entry (FR-017) and makes the
lineage a property of the record rather than a note in a README.

| Property | Value |
| --- | --- |
| Name | Stable across versions |
| Type | MLflow model — the property that enables no-code deployment |
| Source | The Phase 1 run |

### The versioning demonstration

Registering the same model a second time under the same name MUST yield a
distinct higher version, with the earlier version still retrievable afterwards.

Both versions are read back after the second registration. Reading the version
field of a single entry proves a field exists; it does not prove the registry
versions. This costs nothing — registration is metadata over an artifact that
already exists — so there is no reason to assert it instead of showing it.

---

## 2. Endpoint and deployment

| Object | Property | Value |
| --- | --- | --- |
| Endpoint | Kind | **Batch.** A real-time endpoint MUST NOT be created (FR-019) |
| Deployment | Model | The registered version, named explicitly — never `latest` |
| Deployment | Compute | The existing cluster (FR-020) |
| Deployment | Instance count | 1 |
| Deployment | Scoring script | **None.** No-code, derived from the MLflow model ([research.md § R8](../research.md)) |
| Deployment | Output action | Append to a single output file |

Naming an explicit version rather than `latest` is the same discipline the
curated environment gets: a reference that can change under you is not a
reference, and the whole point of Phase 2 is that the registry assigns versions
worth naming.

---

## 3. Scoring input

Drawn from the test split, so the correct predictions are already known from the
baseline.

**Required property (FR-022): the rows MUST have correct predictions that
differ.** If every row were the same class, a deployment that returned a
constant — or one that failed to load the model and fell back to something —
would satisfy the comparison. The input set is checked for both classes before it
is uploaded, and the check is recorded.

---

## 4. The comparison, which is the actual criterion

```text
predictions from the batch endpoint
        │
        │ row for row, in input order
        ▼
predictions computed locally from the DOWNLOADED REGISTERED VERSION
```

**The right-hand side is the registered model pulled back down from the
registry — not the model trained locally during Phase 1.** Comparing against the
local model would demonstrate that scikit-learn is deterministic, which is
already known and is not what Phase 2 is about. Comparing against the downloaded
registered version is what closes the loop: registered → deployed → served → and
the thing served is the thing registered.

| Compared | Rule |
| --- | --- |
| Row count | Exact |
| Row order | Preserved, or joined on an explicit key |
| Predicted class per row | **Exact match, every row** |

A scoring job reaching a completed state MUST NOT be offered as evidence
(FR-021). It proves compute ran.

---

## 5. Closure

Read from the service, not assumed from an elapsed interval (FR-029):

| Check | Required |
| --- | --- |
| Cluster node count | Zero, `Steady`, from ARM — `az ml compute show` returns an empty `node_state_counts`, and an empty field is not a zero (feature 004) |
| Batch endpoint | Exists, holds no allocated compute |
| Online endpoints | **None** |
| Compute instances | **None** |

The batch endpoint is **kept, not deleted**. It holds no compute between scoring
jobs, so it costs nothing, and it is the artifact the exam objective is about.
"Not active" is the requirement; deletion would be tidiness, and tidiness that
destroys the deliverable is not tidiness.

---

## 6. Deferred readings, opened at the start of Phase 2

These come first in the session, because they are the only work in this feature
that expires.

| Reading | Window | Closes |
| --- | --- | --- |
| Measured cost of 2026-08-16 vs. the Phase 1 estimate | 2026-08-16 | SC-007 |
| Load-balancer duration test | 2026-08-16 | SC-013 |

**The load-balancer test, restated so it can still fail** — the original binary
form no longer discriminates, because this feature's own jobs put a
load-balancer row on the day that was supposed to be at rest:

```text
implied_hours = load_balancer_meter_EUR / assumed_rate_EUR_per_hour
```

| If `implied_hours` ≈ | Conclusion |
| --- | --- |
| 2–5 h (job-active windows + ~2 h tail) | Billed only while warm. A resting cluster is free; "leave it running" survives |
| ~24 h | Billed at rest. **The cluster must be deleted at the end of each week**, and the shutdown procedure changes for the rest of the project |

The job-active windows come from the Phase 1 job timestamps, which are collected
anyway for SC-006, so both terms of the comparison are free.

**Carry the caveat into the conclusion**: the rate in the denominator is an Azure
list price recalled from memory, not a measured rate. The two hypotheses differ
by roughly an order of magnitude, which is the only reason the test survives a
rate that is wrong by 50%. A conclusion stated without that caveat would be
exactly the kind of over-confident inference that produced the wrong
load-balancer prediction in the first place.

**Query throttling is expected.** The Cost Management query API returned `429`
repeatedly on 2026-08-16. The exhausted bucket is the client-type quota, with
`retry-after: 12`; the queries-per-hour budget was untouched. Space retries ~20 s
apart rather than sleeping a minute between them, and treat a `429` as a server
response rather than a client-side failure.
