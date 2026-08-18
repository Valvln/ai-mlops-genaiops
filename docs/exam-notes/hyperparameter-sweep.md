# Hyperparameter sweep jobs — documented, not measured

**Status: nothing in this note was run against a subscription.** No sweep job
has ever been submitted by this repository. Every claim here comes from the
Microsoft Learn pages listed under *Sources*, read on 2026-08-18, except where
it explicitly reuses a figure this project measured — those are marked
**measured here** and link to `compute-cost-model.md`.

That distinction is the point of the note. `compute-cost-model.md` earns its
figures by reading Cost Management; this one cannot, so it says what it is.

---

## 1. The five parts of a sweep job

A `type: sweep` job is a *trial* job template plus four decisions. Getting the
vocabulary exact matters more than it looks, because the exam asks which knob
does which job.

| Part | Key | What it decides |
| --- | --- | --- |
| Search space | `search_space` | which values exist |
| Sampling algorithm | `sampling_algorithm` | which of them get tried |
| Objective | `objective.primary_metric`, `objective.goal` | what "better" means |
| Early termination | `early_termination` | which running trials get killed |
| Limits | `limits` | when the whole thing stops |

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/sweepJob.schema.json
type: sweep
trial:
  code: src
  command: >-
    python main.py --learning-rate ${{search_space.learning_rate}}
  environment: azureml:AzureML-sklearn-1.5@latest
compute: azureml:cpu-cluster
sampling_algorithm: random
search_space:
  learning_rate:
    type: uniform
    min_value: 0.01
    max_value: 0.9
objective:
  goal: minimize
  primary_metric: test-multi_logloss
limits:
  max_total_trials: 20
  max_concurrent_trials: 4
  timeout: 7200
```

**The trial's hyperparameters are referenced as `${{search_space.<name>}}`**, not
`${{inputs.<name>}}`. Inputs are the job's fixed inputs; the search space is what
varies per trial. The same job can have both.

---

## 2. The objective is a contract with the training script

> "The name of the primary metric reported by each trial job. The metric must be
> logged in the user's training script, using `mlflow.log_metric()` with the same
> corresponding metric name."

`goal` is `maximize` or `minimize`. Nothing validates that the script actually
logs that metric name — a typo produces trials that run to completion and a
sweep that cannot rank them. **This is the same failure shape as an unconfigured
MLflow tracking URI**: the job goes green having achieved nothing, which
`train.py` was written to refuse (see its `assert_tracking`).

The metric can be logged more than once per trial. Each logging event is one
*interval*, and intervals are the clock that early-termination policies run on —
which is why `evaluation_interval` is counted in metric reports, not in seconds.

---

## 3. Sampling algorithms, and the constraint each carries

| Algorithm | `type` | Expressions it accepts | Early termination |
| --- | --- | --- | --- |
| Random | `random` | discrete **and** continuous | supported |
| Grid | `grid` | **`choice` only** | supported |
| Bayesian | `bayesian` | `choice`, `uniform`, `quniform` | **not supported** |

Three things are worth memorising exactly, because each is a plausible-sounding
distractor away from being wrong:

- **Grid's constraint is on the distribution type, not on the count.** "Grid
  sampling can only be used with `choice` hyperparameters." There is no limit of
  three hyperparameters, or of any number; a grid over `uniform()` is what is
  rejected, because an exhaustive search of a continuous range is not a finite
  object.
- **Bayesian is the one incompatible with early termination.** It chooses each
  new sample from the results of previous ones, so killing a trial mid-flight
  destroys the evidence the next sample is drawn from. Leave `early_termination`
  unset with `bayesian`.
- **Random supports a Sobol rule.** `sampling_algorithm: {type: random, rule:
  sobol, seed: 123}` gives a quasi-random sequence with better space-filling and
  — with the seed — reproducibility. `rule` defaults to `random`.

Bayesian carries a sizing rule of thumb from the documentation: *"a maximum
number of jobs greater than or equal to 20 times the number of hyperparameters
being tuned"*, and lower concurrency converges better, because more trials get
to benefit from finished ones.

### Parameter expressions

Discrete: `choice`, `randint`, `quniform`, `qloguniform`, `qnormal`,
`qlognormal`. Continuous: `uniform`, `loguniform`, `normal`, `lognormal`. The
`q` prefix is a quantiser — `quniform` is `round(uniform(...) / q) * q`, which is
how a continuous range becomes discrete without being enumerated.

---

## 4. Early termination policies

All three take `evaluation_interval` (default `1`) and `delay_evaluation`
(default `0`). `delay_evaluation` exists to stop the policy from killing a trial
that starts slow and finishes best.

| Policy | `type` | Required key | Terminates a trial when |
| --- | --- | --- | --- |
| Bandit | `bandit` | `slack_factor` **or** `slack_amount` | its best metric falls outside the slack from the **best** trial so far |
| Median stopping | `median_stopping` | — | its running average is worse than the **median** of all trials' running averages |
| Truncation selection | `truncation_selection` | `truncation_percentage` | it is in the worst *N* % at this interval |

**Bandit is the one that answers "within X% of the best".** The arithmetic is
worth carrying: with `slack_factor: 0.2` and a best metric of 0.8 at interval 10
on a maximise goal, the cut is `0.8 / (1 + 0.2) = 0.66`. `slack_factor` is a
ratio; `slack_amount` is an absolute difference. Exactly one of the two.

Documentation's own recommendation, useful as a default rather than as trivia:
median stopping with `evaluation_interval: 1`, `delay_evaluation: 5` gives
"approximately 25%-35% savings with no loss on primary metric". Bandit with a
small slack, or truncation with a large percentage, is the aggressive end.

Truncation additionally takes `exclude_finished_jobs`, which decides whether
completed trials count in the ranking used to cut the living ones.

---

## 5. Limits, and what actually caps the bill

| Key | Default | Caps |
| --- | --- | --- |
| `max_total_trials` | `1000` | how many trials run in total |
| `max_concurrent_trials` | = `max_total_trials` | how many run **at once** |
| `timeout` | `5184000` (60 days) | wall-clock for the whole sweep |
| `trial_timeout` | — | wall-clock for one trial |

> "If both `max_total_trials` and `timeout` are specified, the hyperparameter
> tuning experiment terminates when the first of these two thresholds is
> reached."

**`max_concurrent_trials` is not a spending cap, and this is the part the
Domain 2 simulation got wrong.** The bill is node-hours. Node-hours are set by
*how much work is done*, not by how much of it happens simultaneously.
`max_total_trials`, `timeout` and `trial_timeout` bound the work; concurrency
only bounds the wall-clock.

Raising concurrency on a fixed `max_total_trials` therefore leaves the cost
roughly unchanged. Two second-order effects, both **measured here** and both
pointing the same way — *more* concurrency is mildly *cheaper*:

- The load balancer and public IP bill against the **cluster-warm window plus a
  tail of roughly an hour**, not against node count
  (`compute-cost-model.md` § 7.3). Finishing the same trials in a shorter warm
  window shortens that term.
- Each node activation pays a P10 OS disk overhead of ≈0.9 h regardless of how
  short the script is, and pays provisioning plus a 120-second idle tail as node
  time (`compute-cost-model.md` § 7.2, § 7.3). The rule that came out of it —
  *"fewer, longer jobs are materially cheaper than many short ones"* — applies
  to trials unchanged.

Against that, the documentation's own warning about sweeps specifically:

> "Every hyperparameter sweep job restarts the training from scratch, including
> rebuilding the model and *all the data loaders*."

So a sweep of 40 trials pays the per-activation overhead up to 40 times. The
lever on cost is **the number of trials**, and secondarily the amount of work
each one repeats — never the parallelism.

**Concurrency cannot exceed the compute target.** "The number of concurrent
trial jobs is gated on the resources available in the specified compute target."
`max_concurrent_trials: 8` against a cluster with `max_nodes: 4` does not fail
validation and does not scale the cluster past its maximum: it is throttled to
4.

---

## 6. What this note would cost to verify

Stated so the decision to leave it unverified is a decision rather than an
omission. A minimal sweep — 4 trials of the existing decision-tree script on the
existing `Standard_DS1_v2` cluster — would be four short activations from cold,
at the § 7.3 rule of thumb of ≈0.05 € each, so **≈0.2 €**, plus whatever the
warm window overlaps away. It is affordable. It was not run because the Domain 2
result showed that building a thing is what fails to fix it, and because a sweep
adds nothing to the cost model that five cluster jobs have not already settled.

If the retest still shows this area weak, that is the price of settling it.

---

## Sources

- [Hyperparameter tuning a model (v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-tune-hyperparameters)
- [CLI (v2) sweep job YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-sweep)
- [BayesianParameterSampling](https://learn.microsoft.com/en-us/python/api/azureml-train-core/azureml.train.hyperdrive.bayesianparametersampling) — for the early-termination incompatibility
- `compute-cost-model.md` § 7.2, § 7.3 — the node-hour figures reused above
