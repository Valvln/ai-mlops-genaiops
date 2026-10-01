# Responsible AI dashboard and the feature retrieval specification

**Status: documented, not built.** Two exam objectives of *Implement model
registration and versioning* that this repository never touched: evaluating a
model with responsible AI tools, and packaging a feature retrieval
specification with a model. The registered model of feature 005 (an sklearn
decision tree in MLflow format) is the kind of model the dashboard accepts.
Nothing below was run.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objectives: *Evaluate a model by using responsible
AI principles*, *Package a feature retrieval specification with the model
artifact*.

---

## 1. The Responsible AI dashboard

One interface over several open-source tools, plus a **PDF scorecard** for
stakeholders who don't use the workspace.

| Component | Question it answers | Package |
| --- | --- | --- |
| Error analysis | where are errors concentrated, which cohorts | Error Analysis |
| Fairness assessment, model overview | how do metrics differ across sensitive groups (sex, race, age) | **Fairlearn** |
| Data analysis | over- and under-representation, distributions | |
| Model interpretability | which features drive predictions, globally and per row | **InterpretML** |
| Counterfactual what-if | smallest feature change that flips a prediction | **DiCE** |
| Causal inference | effect of an intervention on a real outcome, from historical data | **EconML** |

Learn's stages: **identify** (error analysis, fairness, model overview),
**diagnose** (data analysis, interpretability, counterfactuals), **mitigate**
(standalone tools such as Fairlearn's mitigation algorithms).

Counterfactuals answer the **model's** behaviour ("what change gets a different
outcome from the model"). Causal inference answers the **real world** ("what is
the effect of changing a treatment on the outcome"). Learn pairs
interpretability with causal inference to check whether the features a model
uses have a causal effect.

### Supported models and data

- Regression and classification (binary, multi-class) on **tabular** data.
- **MLflow models registered in Azure ML with a scikit-learn flavor only**,
  exposing `predict()` / `predict_proba()`, loadable in the component
  environment, pickleable.
- **AutoML MLflow models aren't supported**, nor AutoML models registered from
  the UI.
- The UI shows up to **5,000 rows**: downsample first. The constructor's
  `maximum_rows_for_test_dataset` defaults to 5,000.
- Datasets: **MLTable** inputs to the components (the concept page states
  pandas DataFrames in Parquet). At most 10,000 columns. Categorical feature
  names must be listed explicitly.

### Building it

A **pipeline job** of components from the `azureml` registry:

1. **RAI Insights dashboard constructor** (required): model, train and test
   datasets, `target_column_name`, task type.
2. One or more tools: error analysis, explanation, counterfactuals, causal.
3. **Gather RAI Insights dashboard** (required). Optional scorecard component.

- The model comes in through the **Fetch Registered Model** component.
- **A model is required even for a causal-only analysis**: use sklearn's
  `DummyClassifier` or `DummyRegressor`.
- It can also be created from studio for a registered model.

---

## 2. Managed feature store and the feature retrieval specification

A feature store is a **workspace type** that several project workspaces use.
Features are defined once in **feature set specifications**, materialised by
managed Spark into an **offline store (ADLS Gen2)** and optionally an **online
store (Redis)**.

What Learn credits it with:

- **Feature sets are versioned and immutable**, so a new model version can use
  new feature versions without breaking old model versions.
- The same feature pipeline for training and inference, which **avoids
  training/serving skew**.
- **Point-in-time joins** ("time travel") at retrieval, which **avoid data
  leakage**.
- Primary cost: the managed Spark materialization jobs.

### The feature retrieval specification

- A portable list of the features a model uses, generated with
  `generate_feature_retrieval_spec(folder, features)`.
- It is the input of the built-in **feature retrieval component**, which takes
  the spec, the observation data and the timestamp column, and produces
  training data as a managed Spark job.
- **It is packaged with the model.** Name it **`feature_retrieval_spec.yaml`** in
  the model folder so the system recognises it.
- At inference, the same spec drives feature lookup, so training and inference
  read the same features.
- The model's **Feature sets** tab lists the feature sets it depends on, and a
  feature set lists the models that use it.
- In production, a change to the spec in source control can trigger the
  training pipeline through CI/CD.

Using the spec and the component is optional. `get_offline_features()` is the
programmatic alternative.

---

## 3. What this repository measured, and what it did not

**Measured:** nothing on either topic. Adjacent facts:

- `ai300-decision-tree` version 1 is an `mlflow_model` with `python_function`
  and `sklearn` flavors, registered from its run. It meets the dashboard's model
  requirement on paper.
- Training data is a single CSV read through a datastore. No feature store,
  no time column, so point-in-time correctness was never a question here.

**Not measured:** any dashboard, scorecard, feature store, retrieval spec.

---

## 4. What this note would cost to verify

A dashboard with error analysis and explanation on the existing model is a
pipeline of three or four components on the existing cluster: a few node
activations, under 0.30 €. It needs train and test data as MLTable. A feature
store adds managed Spark jobs, priced per run, and an ADLS Gen2 account.

---

## Sources

- [Assess AI systems by using the Responsible AI dashboard](https://learn.microsoft.com/en-us/azure/machine-learning/concept-responsible-ai-dashboard): read 2026-10-01 (ms.date 2025-10-13); § 1
- [Generate Responsible AI insights with YAML and Python](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-responsible-ai-insights-sdk-cli): read 2026-10-01 (ms.date 2026-03-12); § 1 building it
- [What is managed feature store?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-what-is-managed-feature-store): read 2026-10-01 (ms.date 2025-10-30); § 2
- [Tutorial 2: Experiment and train models by using features](https://learn.microsoft.com/en-us/azure/machine-learning/tutorial-experiment-train-models-using-features): read 2026-10-01 (ms.date 2024-09-30); § 2 retrieval specification
- `specs/005-training-job-batch-endpoint/results.md`: § 3
