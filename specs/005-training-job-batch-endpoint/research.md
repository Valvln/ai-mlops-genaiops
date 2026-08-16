# Research: From a job that runs to a model that answers

**Feature**: 005 · **Date**: 2026-08-16

Decisions taken before implementation, each with the reasoning that produced it
and the alternatives rejected. Where a decision rests on a claim that has not
been observed, the claim is written as a **prediction** with the observation that
will confirm or embarrass it. Feature 004 scored 5 of 7 on its predictions; the
two misses were worth more than the five hits.

---

## R1 — Does the workspace configure MLflow tracking, or must the job declare it?

**This is the question the specification forbids answering from memory (FR-009),
so it is written here as a prediction and settled by the first job.**

**Prediction**: Azure ML injects `MLFLOW_TRACKING_URI` into the job container
automatically for any job submitted to the workspace, so a script calling
`mlflow.log_metric` reaches the workspace with no configuration of its own. The
tracking URI is expected to be an `azureml://` URI naming this workspace.

**Why it matters that this is verified rather than assumed.** If the variable is
absent, MLflow does not fail. It silently falls back to a local `mlruns/`
directory on the compute node, the job succeeds, the script exits zero, and every
metric is destroyed with the node at scale-down. That is a green run with nothing
tracked — precisely the failure mode this repository keeps producing, and it
would be discovered a day later when the run cannot be found.

**Decision**: the training script settles it in its own first seconds, before it
trains anything:

1. Report whether `MLFLOW_TRACKING_URI` is present in the environment, and its
   value.
2. Report what `mlflow.get_tracking_uri()` actually resolves to, which is not
   necessarily the same thing.
3. **Assert** that the resolved URI is `azureml`-backed, and exit non-zero with a
   named error if it is not.

The assertion is the load-bearing part. Without it the script cannot fail on the
axis that matters, and a check that cannot fail is not a check.

**Alternatives rejected**:

- *Read the documentation and assume.* The specification forbids it, and the
  documentation describes a default that a curated environment or a job setting
  could override.
- *Run a separate cheap probe job first.* Two cluster activations instead of one.
  Billing runs from allocation (§ 7.2 of the cost model), so a probe job costs
  roughly what the real job costs — about 0.03 € to learn something the real job
  reports for free in its first three lines.

---

## R2 — Does the curated environment actually contain MLflow?

**Prediction**: yes. `sklearn-1.5` version 52 is described as containing "the
Azure ML SDK and additional python packages", and the Azure ML SDK pulls
`azureml-mlflow`, which is the plugin that teaches MLflow how to talk to an
`azureml://` URI. Both `mlflow` and `azureml-mlflow` are expected to be present.

**Risk if wrong**: `mlflow` present but `azureml-mlflow` absent is the dangerous
combination, because the import succeeds and the `azureml://` URI is then
unroutable. This is caught by R1's assertion rather than by hope.

**Decision**: the script prints the installed versions of `mlflow`,
`azureml-mlflow`, `scikit-learn`, `numpy` and `pandas` before training. This
costs nothing, and it is also the record that makes the local baseline's
version match auditable rather than claimed.

**Fallback if the prediction fails**: the job gains a pip dependency layer and is
resubmitted, at the cost of one further cluster activation (≈0.03 €). Bounded and
acceptable. A custom Docker image is **not** an option and deliberately so — it
would require a container registry, which `main.bicep` omits precisely so that
none is provisioned.

---

## R3 — Which identity writes the tracking record and the model artifact?

Feature 004 established the rule that decides this: with `identity: managed`, the
job runs as the **compute cluster's** system-assigned identity, and that
principal holds exactly one role assignment — `Storage Blob Data Reader`, scoped
to the `training-data` container. Read-only, on the wrong container for writing
anything.

Tracking records and model artifacts are written to the workspace's **default**
storage container, which that grant does not cover.

**Prediction, held loosely**: this will **not** fail, because run-history and
artifact upload are performed by the run infrastructure using the run's own
token rather than by the user code using the compute identity. The evidence is
from feature 004 itself: that job ran with `identity: managed` and its
`user_logs/std_log.txt` was written to the workspace default store regardless.

**Confidence is low, and the asymmetry is the point.** `identity: managed`
selects the identity for *user code's data access*. Whether MLflow's artifact
upload counts as user-code data access or as platform activity is exactly the
distinction feature 004 showed this project getting wrong in the other direction.

**Decision**: do not pre-grant anything. Discover by failing, per FR-023. If a
refusal arrives:

1. Establish it is a server-side refusal, not a client-side failure, a wrong
   path, or an empty result (FR-025). Feature 004 recorded that not every refusal
   says `AuthorizationFailed` — the same run returned an ARM `AuthorizationFailed`
   and an Azure ML `UserError` with `ForbiddenError` buried in an inner error.
2. Add exactly the operation and scope the refusal names, to the principal it
   names, as a role assignment in `infra/main.bicep`.
3. Record the failing job name as the grant's provenance.

**Note the two authority loops are different, and the handover conflated them:**

| Loop | Artifact | What it authorises | Exercised by |
| --- | --- | --- | --- |
| Deployment authority | `infra/ci-identity.bicep` | ARM operations CI may perform | Adding a resource type to the template |
| Workload authority | `infra/main.bicep` role assignments | Data-plane access an identity holds | A job being refused at runtime |

A runtime refusal in this feature belongs to the **second** loop. It touches
`ci-identity.bicep` only if the fix adds a resource type CI has never deployed —
and a role assignment is not one, because `roleAssignments/write` has been in the
CI role since feature 002.

**Cost consequence**: a grant means editing `main.bicep`, which means a gated CI
deployment the author must approve. Budgeted as one gated run in Phase 1, not
assumed to be unnecessary.

---

## R4 — Which estimator, given the criterion is cross-platform agreement?

The success criterion is not accuracy. It is that metrics computed on a Linux
node inside a curated container agree with metrics computed on the author's macOS
machine, to a tolerance tight enough to be meaningful. **The estimator must
therefore be chosen for reproducibility across platforms, not for being the
obvious teaching example.**

**Decision: `DecisionTreeClassifier(max_depth=4, random_state=42)`.** The values
are pinned in [data-model.md § 2](./data-model.md), which both `train.py` and
`baseline.py` read from — a divergence between the two scripts would present as a
metric disagreement, and that is the one cause the comparison cannot tell apart
from a real tracking fault.

**Rationale**: tree fitting is comparison-and-counting over the data. It does not
route through BLAS, so it does not inherit the difference between Apple's
Accelerate framework on the author's machine and OpenBLAS in an Ubuntu container.
Given identical bytes and a fixed `random_state` to break split ties, the fitted
tree — and therefore every prediction — is expected to be **identical**, not
merely close.

**Alternative rejected: `LogisticRegression`.** The canonical choice, and the
wrong one here. `lbfgs` is an iterative optimiser running on top of BLAS;
coefficients can differ in the last bits between platforms. Usually that is
invisible. But predictions near the decision boundary flip on those bits, and a
flipped prediction moves accuracy by a discrete step — so the comparison would
fail *loudly and intermittently*, on an axis that has nothing to do with what is
being tested. A criterion that fails for the wrong reason is as broken as one
that passes for the wrong reason, which is the mistake feature 004 made with its
"zero `Modify`" acceptance criterion.

**Alternative rejected: `RandomForestClassifier`.** Deterministic given a seed,
but it multiplies fit time for no gain, and the point is that training time be a
negligible fraction of billed time (FR-003).

**Consequence for the tolerance**: because exact agreement is expected, the
comparison is written in two parts — the prediction vector must match
**exactly**, and metrics must match within `1e-9`. Setting a loose tolerance
"just in case" would discard the discriminating power the estimator choice was
made to buy.

---

## R5 — How is the synthetic data generated so it is reproducible?

**Decision: NumPy's `default_rng(seed)` Generator API, with a documented
closed-form procedure, written to CSV with fixed float formatting.**

**Rationale**: NumPy guarantees stream reproducibility for `default_rng` across
versions. The legacy `RandomState` API carries the same guarantee, but
`sklearn.datasets.make_classification` does **not** — it is library code whose
internals may change between scikit-learn releases, so regenerating the dataset
after a version bump could silently produce different bytes. Since FR-001
requires that identical bytes be reproducible from the recorded procedure, the
generator must not depend on a library that is free to change it.

**The bytes are the ground truth, not the procedure.** The file is generated
once, locally, and uploaded. The job reads *those bytes*. The local baseline
reads *the same local file*. So even if regeneration ever diverged, the
comparison being made is still between two reads of one artifact — the fixed seed
buys reproducibility of the setup, not the validity of the comparison.

**Shape**: 2,000 rows, 5 numeric features, one binary label. Large enough that
accuracy is not degenerate and both classes are well populated; small enough
(~200 KB) that fitting is milliseconds against a job whose billed time is
measured in minutes.

**Split**: **positional, not random** — the first 1,500 rows train, the last 500
test. There is no RNG in the split at all, so there is no seed to agree about and
no library version that can reinterpret it. The rows are already in random order
by construction, so a positional split is not a biased one.

---

## R6 — How does the local baseline match the remote environment?

The curated environment `sklearn-1.5` version 52 reports: **Ubuntu 20.04, Python
3.10, scikit-learn 1.5**. Version 52 was confirmed to still be the latest on
2026-08-16, so feature 004's pin remains current.

**Decision**: build the local baseline environment with `uv`, pinned to Python
3.10 and scikit-learn 1.5.x, in a `.venv` that is already gitignored. The pinned
specification is tracked; the environment is not.

**Rationale**: the author's default interpreter is Python 3.14, for which
scikit-learn 1.5 has no wheels. More importantly, comparing metrics from
scikit-learn 1.5 against a baseline computed on some other version would make any
disagreement uninterpretable — it could be the job, or it could be the library.
The estimator choice in R4 removes the platform variable; pinning removes the
version variable. What remains, if the comparison fails, is a real finding.

**Residual risk, stated rather than hidden**: the curated environment's tag says
`Scikit-learn: 1.5`, not a patch version. The exact patch installed in the image
is unknown until the job reports it (R2), so the local pin may differ in patch.
For a decision tree this is very unlikely to matter, and if a disagreement does
appear, the versions printed by the job are the first place to look.

---

## R7 — Where is the batch endpoint declared: the template, or a workload file?

**Decision: a workload definition in `mlops/`, applied with `az ml`. Not Bicep,
and not through the CI gate.**

**Rationale**, in the order the reasons actually weigh:

1. **Precedent within the repository already draws this line.** Feature 004 put
   the *infrastructure* — cluster, data store, role assignment — in
   `main.bicep`, and put the *workload* — the job — in `mlops/datastore-check/job.yml`.
   A batch endpoint and its deployment are workload: they name a model version,
   a scoring behaviour and a mini-batch size, and they are meaningless without
   the model the job produced.
2. **A Bicep deployment cannot cleanly express the dependency.** The deployment
   references a model version that does not exist until the training job has run
   and been registered. Expressing that in a template means a parameter carrying
   a runtime-produced value, which is a template that lies about being
   declarative.
3. **Schedule risk, and it is the decisive one.** Adding
   `batchEndpoints/write` and `batchEndpoints/deployments/write` to the CI role
   is discovered by failing — feature 004 needed three gated attempts to find
   five operations. Each attempt needs the author present to approve the gate.
   Spending Phase 2's morning on gated approvals to deploy an object the exam
   objective describes as "deploy a batch endpoint" would be spending the budget
   on the wrong noun.

**What this decision buys**: feature 005 adds **no new resource type to
`main.bicep`**, so it requires **no CI role change and no gated deployment** —
unless R3's refusal materialises, which is the one contingency that would put a
gated run back on the schedule.

**What it costs, stated plainly**: the batch endpoint is not reproducible from
the template. Recreating the environment from scratch would recreate the cluster
and data store but not the endpoint. That is accepted for a learning artifact
bound to a runtime-produced model version, and it is recorded here so it is a
decision rather than an omission.

---

## R8 — No-code deployment, and why the logging format is chosen for it

**Decision: log the model in MLflow format, register it as an MLflow model, and
deploy it with no scoring script.**

**Rationale**: a batch deployment of an MLflow-format model does not need a
scoring script or an inference environment — Azure ML derives both from the
model's own metadata. That removes two files, two failure modes, and the
question of whether a scoring bug or a serving bug caused a wrong prediction.

It also means the format decision in Phase 1 has a consequence in Phase 2, which
is worth noticing: logging the model with a generic file upload would still
satisfy "an artifact exists" while quietly forcing a scoring script the next day.

**Consequence for FR-021**: with no scoring script of ours in the path, a
disagreement between the endpoint's predictions and the local baseline's is
attributable to the model or the serving layer, not to code written for the
occasion.

---

## R9 — The batch endpoint's identity is a third principal

Three distinct principals are now in play, and feature 004's rule — *the grant
that matters is the one held by the identity that actually performs the
operation* — applies to each:

| Principal | Performs |
| --- | --- |
| The author | Uploading data, submitting jobs, reading the registry |
| The compute cluster's identity | Reading training data inside the job |
| The batch endpoint's identity | Reading the model, reading scoring input, writing predictions |

**Prediction**: the endpoint's identity will need access it does not have by
default, most likely to write its output. **Confidence deliberately low** — this
is the same shape of question that produced feature 004's most wrong prediction.

**Decision**: same loop as R3. Discover by failing, establish the refusal is
server-side, grant exactly what it names, record the job that demanded it.

---

## R10 — Cost estimate, at the rates measured this morning

Estimated **before** the work, per FR-027, using § 7.2 of the cost model rather
than the node rate alone. The estimate that this replaces was wrong by 4.6×
because it priced only the virtual machine.

Per cluster activation, for a job of a few minutes:

| Component | Rate | Assumed | Cost |
| --- | --- | --- | --- |
| VM + OS disk | 0.082 €/node-hour | ~8.3 min billed | 0.011 € |
| LB + public IP | 0.025 €/hour warm | shared across the session's window | — |

| Phase | Activations | Node cost | Warm-window cost | Total |
| --- | --- | --- | --- | --- |
| Phase 1 | 2–3 | ≈0.034 € | ≈2.5 h → 0.063 € | **≈0.10 €** |
| Phase 2 | 1–2 | ≈0.023 € | ≈2.0 h → 0.050 € | **≈0.07 €** |
| Feature | | | | **≈0.17 €** |

**The warm-window term dominates, and that changes how the day should be run.**
Because the load balancer bills per hour of cluster warmth rather than per job,
three jobs run back to back within one warm window cost barely more than one job.
Three jobs spread across the day, each re-warming the cluster, cost three times
the warm-window term. **Batch the submissions, do not spread them** — this is
FR-026 given a number.

**Agreement factor for SC-007**: the measured figure for 2026-08-16 is expected
to agree with this estimate **within a factor of 2**. Stated now, before the
measurement, because an agreement threshold chosen after seeing the answer is not
a threshold.

---

## R11 — The load-balancer test, restated so it can still fail

Feature 004 deferred this to a day at rest. This feature's jobs run on that day,
so the original binary test — is there a load-balancer row — now returns "yes"
under both hypotheses and discriminates nothing.

**Decision**: divide the meter by its rate and compare the implied duration
against two predictions that differ by an order of magnitude.

| Hypothesis | Implied LB duration on 2026-08-16 |
| --- | --- |
| Billed only while warm | ≈ (sum of job-active windows) + ~2 h tail — call it **2–5 h** |
| Billed at rest as well | **≈24 h** |

**Prediction**: the warm-only hypothesis, at 2–5 h. It rests on the 15/08
reading, where the implied LB duration was ≈2.1 h against 7.4 h of elapsed day —
the balancer was demonstrably torn down rather than left standing.

**The known weakness, stated because it is inherited**: the rate used in the
division is an Azure list price recalled from memory, not a measured rate. A
wrong rate scales the implied duration proportionally. The 2–5 h and ~24 h
hypotheses are far enough apart to survive a rate that is wrong by 50%, which is
the only reason this test is usable at all. **Any conclusion must carry that
caveat**, and the requirement to record it is in the spec's Assumptions.

**Supporting evidence to collect the same day, free**: the job-active windows
come from the jobs' own timestamps, which are recorded anyway for SC-006. So the
comparison has both of its terms without an extra query.

---

## R12 — What is deliberately not researched

| Not researched | Because |
| --- | --- |
| The cluster's and data store's configuration | Built and verified in feature 004; the specification's Assumptions consume them as given |
| Whether a compute instance would be more convenient | Cut on cost in week 1; ~25 €/month while merely stopped |
| Model accuracy, feature engineering, class balance | Explicitly out of scope; the estimator is chosen for determinism |
| Real-time endpoint mechanics | Cut from construction for week 2, retained as exam material |
| Whether the author can read job logs from the CLI | Answered in feature 004: no, because the author holds no data-plane role. Logs are read with the account key |
