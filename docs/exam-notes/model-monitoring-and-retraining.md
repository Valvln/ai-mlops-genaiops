# Model monitoring and retraining triggers — documented, not measured

**Status: no monitor has ever been created by this repository, and none can be
honestly created here.** Model monitoring compares production inference data
against reference data. This project has no production traffic; a monitor built
on synthetic replays of its own training file would compare a distribution to
itself and report the absence of drift as a result. That would be a green check
that proves nothing — the failure mode this repository already knows by name.

Everything below comes from the Microsoft Learn pages under *Sources*, read on
2026-08-18. Nothing is measured.

---

## 1. The mechanism, in four steps

1. Azure ML computes the statistical distribution of each feature in the
   **reference data** — the baseline.
2. It computes the same distribution over the **latest production data**.
3. It runs a statistical test, or computes a distance score, between the two.
4. If the score crosses a **user-specified threshold**, it raises an alert.

Two consequences that the exam leans on:

- **Drift is a difference between distributions, not an error rate.** No labels
  are involved in steps 1–3 for most signals. A drifting model may still be
  perfectly accurate; a stable one may be quietly wrong.
- **The threshold is yours.** There is no correct default that Azure supplies and
  no notion of drift that exists independently of the number you chose.

---

## 2. The prerequisite that gates everything

**Production inference data must be collected before any of this works.**

| Where the model runs | Who collects |
| --- | --- |
| Azure ML **online endpoint** | Azure ML **model data collector**, automatically |
| Azure ML **batch endpoint** | **you** |
| **Outside** Azure ML | **you** |

> "If you deploy a model outside of Azure Machine Learning or to an Azure Machine
> Learning batch endpoint, you're responsible for collecting production inference
> data that you can then use for Azure Machine Learning model monitoring."

This is why "just add a monitor" is not a small step for a batch-only
deployment, and it is exactly this repository's situation.

Monitoring jobs run on **Spark**. The documentation's own caveat: *"avoid using
`MLTable` whenever possible with model monitoring jobs. Only basic `MLTable`
files have guaranteed support."*

---

## 3. The five built-in signals

| Signal | Compares | Reference | Needs ground truth |
| --- | --- | --- | --- |
| **Data drift** | model **inputs** | training data, or recent production | no |
| **Prediction drift** | model **outputs** | validation data, or recent production | no |
| **Data quality** | input integrity | training data, or recent production | no |
| **Feature attribution drift** (preview) | feature **importance** | **training data — required** | no |
| **Model performance** (preview) | outputs vs actuals | **ground truth — required** | **yes** |

**Only one of the five needs labels.** That single row is the answer to "you have
no ground truth in production, so what can still detect degradation": prediction
drift and feature attribution drift, both of which compare the model against its
own past rather than against the truth.

Feature attribution drift is the subtler of the two — it watches *which* features
the model is leaning on. A model whose input distributions are stable but whose
attribution has shifted is being driven by different evidence than it was trained
on, which is an early warning that no accuracy metric can give you without
labels.

### Metrics per signal

| Signal | Metrics |
| --- | --- |
| Data drift | Jensen-Shannon Distance, Population Stability Index, Normalized Wasserstein Distance, Two-Sample Kolmogorov-Smirnov Test, Pearson's Chi-Squared Test |
| Prediction drift | the same five, plus Chebyshev Distance |
| Data quality | null value rate, data type error rate, out-of-bounds rate |
| Feature attribution drift | normalized discounted cumulative gain |
| Model performance | accuracy / precision / recall (classification); MAE / MSE / RMSE (regression) |

The three data-quality metrics are all rates over the production window, and all
three are defined against the **reference** data: the data type is *inferred*
from the reference, and the acceptable range or category set is *taken* from the
reference — a numeric interval `[min, max]`, or the set of values that appeared.
A new legitimate category is therefore an out-of-bounds event.

---

## 4. Reference data selection

The documentation gives a specific pairing, and it is not arbitrary:

- **Data drift and data quality** → use the **training** data as baseline.
- **Prediction drift** → use the **validation** data as baseline.
- **Feature attribution drift** → training data is **required**, not a choice.
- **Model performance** → ground truth, required.

Recent past production data is allowed as a baseline for the first three, which
detects *change* rather than *divergence from training*. Both are useful; they
answer different questions, and a monitor that uses recent production as its own
baseline will not notice a slow drift that the training-data baseline catches
immediately.

---

## 5. Lookback windows

Two properties, in ISO 8601 durations, on each of `production_data` and
`reference_data`:

| Property | Default |
| --- | --- |
| `data_window.lookback_window_size` | production: the monitoring frequency; reference: the full dataset |
| `data_window.lookback_window_offset` | production: `P0D`; reference: **2 × the production window size** |

`window_start_date` / `window_end_date` on the reference pin a **fixed** window
instead of a rolling one.

**The windows must not overlap**, or the baseline contains the data being tested
against it. The documented rule: the reference offset must be **≥ production
window size + production offset**. The reference default of 2× the production
window exists precisely to guarantee this without anyone thinking about it.

The offset on the production side is for excluding data, not for shifting the
schedule — the documentation's example is a Monday run that skips the weekend
with `lookback_window_size: P5D`, `lookback_window_offset: P2D`.

Frequency should follow data volume, not habit: daily only if daily traffic is
enough for the statistics to mean anything, otherwise weekly or monthly.

---

## 6. Who starts the retraining

**The monitor does not.** It raises an event; something else acts on it.

> "you can set thresholds for these metrics to trigger alerts about model or data
> anomalies via Azure Machine Learning or **Azure Event Grid**"
>
> "if the accuracy of your classification model in production dips below a
> certain threshold, you can **use Event Grid to begin a retraining job** that
> uses collected ground truth data"

The chain is: **detection → event → handler → pipeline.** The handler is an Azure
Function, a Logic App, a Data Factory pipeline, an Event Hub consumer, or a
webhook. Retraining is not a property of the registered model, it is not
automatic, and it is not "always manual" — it is *yours to automate*, out of
decoupled parts.

### Azure ML event types in Event Grid

| Event type | Raised when |
| --- | --- |
| `Microsoft.MachineLearningServices.RunCompleted` | an experiment run completes |
| `Microsoft.MachineLearningServices.ModelRegistered` | a model or model version is registered |
| `Microsoft.MachineLearningServices.ModelDeployed` | one or more models are deployed to an endpoint |
| `Microsoft.MachineLearningServices.RunStatusChanged` | a run's status changes |

Subscriptions filter by event type, by subject prefix/suffix
(`models/{modelName}:{modelVersion}`, `experiments/{id}/runs/{id}`), or by
advanced filters on the event payload — `--advanced-filter data.ModelTags.key1
StringIn value1`. Only a **contributor or owner** of the workspace can create
event subscriptions.

```bash
az eventgrid event-subscription create --name <name> \
  --source-resource-id /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{ws} \
  --endpoint-type eventhub --endpoint <resource-id> \
  --included-event-types Microsoft.MachineLearningServices.ModelRegistered \
  --subject-begins-with "models/mymodelname"
```

### The trap worth memorising

> "**Failed or canceled Azure Machine Learning operations don't trigger an
> event.** For example, if a model deployment fails,
> `Microsoft.MachineLearningServices.ModelDeployed` isn't triggered."

An automation built only on these events is **blind to failure**. It sees the
green path and nothing else — which is, in a different costume, the recurring
defect of this repository: a check that passes while its objective is missed.
Anything that must react to a failure has to poll the operation status, not wait
for an event that will never arrive.

Other documented consumer rules: events can arrive **out of order and delayed**
(use `sequencer` and `etag`), several subscriptions can route to one handler (so
check the topic), and unknown fields should be ignored rather than rejected.

---

## 7. Authentication for the monitor's own data access

Credential-less is the supported path and takes three steps: create a
**user-assigned managed identity**, attach it to the workspace, grant it access
to the datastore holding the collected inference data, and set the workspace
property `systemDatastoresAuthMode` to `'identity'`. Otherwise the datastore
needs stored credentials.

This is the third time in this repository that the operative question is *which
identity performs the operation* — after the compute cluster's identity reading
training data, and the compute cluster's identity (not the endpoint's) mounting
the model for batch scoring.

---

## 8. Why this was not built, stated as a decision

Not cost. A monitor's Spark job is cheap and an online endpoint for two hours is
≈0.12 €. It was not built because **the artifact would have been dishonest**: a
monitor needs production traffic to compare against a baseline, this project has
none, and manufacturing some would produce a passing monitor that measured
nothing. The repository's standing rule is that a check must be able to fail on
the axis being tested.

The honest alternative is this note plus a retest. If Domain 2's retest still
shows monitoring weak, the next step is not a fake monitor — it is an online
endpoint with data collection enabled and a genuinely shifted input file, so the
monitor has something real to disagree with.

---

## Sources

- [Model monitoring in production](https://learn.microsoft.com/en-us/azure/machine-learning/concept-model-monitoring)
- [Trigger events in ML workflows (Event Grid)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-event-grid)
- [Azure Event Grid event schema for Azure Machine Learning](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-machine-learning)
- [Collect production data from models deployed for real-time inferencing](https://learn.microsoft.com/en-us/azure/machine-learning/concept-data-collection)
