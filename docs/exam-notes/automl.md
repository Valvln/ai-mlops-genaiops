# Automated machine learning (AutoML)

**Status: documented, not built.** AutoML was cut on 2026-08-15: it runs many
trials on compute billed by the hour, for a capability the exam asks you to
choose and configure. Nothing below was run against a subscription.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objective: *Use automated machine learning to
explore optimal models*.

---

## 1. What AutoML does

AutoML runs many trials in parallel, each pairing an algorithm with
hyperparameters and featurization, scores each against a **primary metric**,
and stops at the exit criteria. You don't pick the algorithm.

| Task family | Tasks |
| --- | --- |
| tabular | classification, regression, forecasting |
| computer vision | multi-class and multi-label image classification, object detection, instance segmentation |
| NLP | text classification (multi-class, multi-label), named entity recognition |

Vision and NLP are authored with the Python SDK. Tabular works from SDK, CLI or
studio.

---

## 2. Data and validation

- **Training data must be an `MLTable`** in SDK and CLI v2. v1 tabular datasets
  are accepted for compatibility.
- The **target column** must be in the data.
- Without `validation_data` or `n_cross_validation`, the default depends on size:

| Training rows | Default validation |
| --- | --- |
| more than 20,000 | train/validation split, **10%** held out |
| 1,000 to 20,000 | cross-validation, **3 folds** |
| fewer than 1,000 | cross-validation, **10 folds** |

- The same validation data serves every iteration, which biases the final
  score. **Test data** (preview) scores the recommended model at the end.

---

## 3. Compute

AutoML with SDK v2 or CLI v2 runs on a **compute cluster** or a **compute
instance**.

- Each node runs **one child run at a time**.
- **`max_concurrent_trials`** defaults to **1**. Learn: set it to the number of
  cluster nodes, and use a dedicated cluster per experiment. On a compute
  instance, set it to the number of cores.
- Child runs can share a cluster that is busy with another experiment; they
  queue for free nodes.

---

## 4. Configuration

### Primary metric

| Task | Metrics | Learn's guidance |
| --- | --- | --- |
| classification | `accuracy`, `AUC_weighted`, `average_precision_score_weighted`, `norm_macro_recall`, `precision_score_weighted` | threshold-dependent metrics (accuracy, recall, precision) optimise poorly on **small or imbalanced** data; prefer **`AUC_weighted`** there |
| regression, forecasting | `normalized_root_mean_squared_error`, `r2_score`, `normalized_mean_absolute_error`, `spearman_correlation` | squared error punishes large errors more; `spearman_correlation` when rank matters |
| multi-label text, NER | `accuracy` only | |

No primary metric measures **relative** error. To optimise for a percentage
error, run with a supported metric and then pick the model by
`mean_absolute_percentage_error`.

### Algorithms

`allowed_training_algorithms` and `blocked_training_algorithms` narrow the
search. Forecasting adds AutoARIMA, Prophet, TCNForecaster and others.

### Featurization

`mode: auto` (default), `off`, or `custom`. **Featurization becomes part of the
model:** the same transformations apply automatically to scoring input.

### Exit criteria (`limits`)

| Setting | Default |
| --- | --- |
| `timeout_minutes` | 6 days (8,640 min); at 60 minutes or less, data must be at most 10,000,000 rows × columns |
| `trial_timeout_minutes` | 1 month (43,200 min) |
| `max_trials` | 1,000 |
| `max_concurrent_trials` | 1 |
| `enable_early_termination` | ends the job when the score stops improving |

With no exit criterion, the job runs until the primary metric stops improving.

### Ensembles

On by default, as the final iterations: **voting** (weighted average) and
**stacking** (meta-model: LogisticRegression for classification, ElasticNet for
regression). Caruana selection starts from up to five models within 5% of the
best score.

---

## 5. Results and reproducibility

- **Repeated runs with identical settings can give different models and
  scores.** The algorithms have inherent randomness.
- Studio shows the featurization summary, the hyperparameters and the generated
  training code for a model.
- One-click deployment from studio for registered models.
- **The AutoML scoring script works for online endpoints only.** A batch
  deployment of an AutoML model needs its own scoring script.
- The Responsible AI dashboard **doesn't support AutoML MLflow models**.
- AutoML models can be exported to **ONNX**.

---

## 6. AutoML in pipelines and at scale

- An AutoML job can be a pipeline step, between data preparation and model
  registration.
- **Distributed training** exists for **LightGBM** (classification, regression,
  about 1 TB) and **TCNForecaster** (forecasting, about 200 GB):
  `training_mode: distributed` plus `max_nodes`, at least **4** for
  classification and regression. In that mode, cross-validation, ensembles,
  ONNX and code generation aren't supported, and **`max_concurrent_trials` is
  ignored**: trials run one after another.

---

## 7. What this repository measured, and what it did not

**Measured:** nothing on AutoML. Two adjacent measurements apply:

- **Cost is set by node time.** Each trial is a child run on a node, and a node
  activation from cold costs about 0.05 € on `Standard_DS1_v2`
  (`compute-cost-model.md` § 7.3).
- **A cluster never exceeds its `max_nodes`.** Concurrency above the node count
  queues (`hyperparameter-sweep.md` § 5).

**Not measured:** any AutoML job, featurization, ensembles, default validation.

---

## 8. What this note would cost to verify

A classification job on a small MLTable with `max_trials: 5`,
`max_concurrent_trials: 2`, `timeout_minutes: 30` on the existing two-node
cluster, ensembles disabled: two node activations and up to 30 minutes of two
`Standard_DS1_v2` nodes, under 0.10 € of compute.

---

## Sources

- [What is automated machine learning (AutoML)?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-automated-ml): read 2026-10-01 (ms.date 2025-11-24); §§ 1, 2, 4 ensembles
- [Set up AutoML training for tabular data with the Azure Machine Learning CLI and Python SDK](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-configure-auto-train): read 2026-10-01 (ms.date 2026-08-21); §§ 2–6
- [Deploy models for scoring in batch endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-batch-model-deployments): read 2026-10-01 (ms.date 2026-08-21); AutoML scoring script
- [Assess AI systems by using the Responsible AI dashboard](https://learn.microsoft.com/en-us/azure/machine-learning/concept-responsible-ai-dashboard): read 2026-10-01 (ms.date 2025-10-13); AutoML limitation
- `compute-cost-model.md` § 7.3, `hyperparameter-sweep.md` § 5: § 7
