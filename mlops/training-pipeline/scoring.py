"""Batch scoring entry point.

**This file exists because the no-code path is not available on this platform**,
not because it was preferred. research.md R8 chose to log the model in MLflow
format specifically so that Azure ML would derive the scoring behaviour and the
environment itself, removing two files and two failure modes. That decision was
sound and is defeated by a dependency conflict outside this repository:

    mlflow 3.13.0                 requires pyarrow >=4.0.0,<25
    azureml-dataset-runtime[fuse] requires pyarrow >=0.17.0,<4.0.0

Azure ML's batch inference stack installs `azureml-dataset-runtime` when it
synthesises an environment from a model's `conda.yaml`, and the intersection of
those two ranges is empty for all 35 published versions of that package. The
synthesised environment cannot resolve, so the image build fails before any node
is allocated. See results.md.

With an environment named explicitly, no synthesis happens — but the conflict
still constrains what may be *in* that environment. The batch runtime needs
`azureml-dataset-runtime`, so mlflow cannot be installed alongside it, so
`mlflow.pyfunc.load_model` is not available at serving time.

The model is therefore loaded from the sklearn flavor's pickle directly. The
MLmodel file names it: `pickled_model: model.pkl`, `serialization_format:
cloudpickle`, `sklearn_version: 1.5.2`. The serving environment pins those same
versions, because a pickle is only portable across the versions that made it.

What this costs, stated rather than hidden: the model is still registered and
deployed as an MLflow model, but the MLflow format buys nothing at serving time
on this platform. R8 chose that format for exactly the benefit that turns out
not to be available.

The output carries `row_index` rather than relying on row order. Batch scoring
returns rows per mini-batch and the framework appends them; with a single input
file that ordering happens to be stable, but "happens to be" is not a property
the comparison should rest on. An explicit join key makes the check verifiable
instead of lucky.
"""

from __future__ import annotations

import os
from pathlib import Path

import cloudpickle
import numpy as np
import pandas as pd
import sklearn

model = None


def _find_model_dir(root: Path) -> Path:
    """Locate the directory holding MLmodel under AZUREML_MODEL_DIR.

    The registered model is unpacked under a path that depends on how it was
    registered, so it is discovered rather than hard-coded — a wrong guess here
    fails at serving time, which is the most expensive place to find out.
    """
    if (root / "MLmodel").is_file():
        return root
    for candidate in sorted(root.rglob("MLmodel")):
        return candidate.parent
    raise RuntimeError(f"no MLmodel found under {root}: {[p.name for p in root.rglob('*')][:20]}")


def init() -> None:
    global model
    root = Path(os.environ["AZUREML_MODEL_DIR"])
    model_dir = _find_model_dir(root)
    print(f"SCORING-INIT model_dir={model_dir}")
    print(
        f"SCORING-INIT sklearn={sklearn.__version__} pandas={pd.__version__} "
        f"numpy={np.__version__} cloudpickle={cloudpickle.__version__}"
    )
    with (model_dir / "model.pkl").open("rb") as handle:
        model = cloudpickle.load(handle)
    print(f"SCORING-INIT model loaded: {type(model).__name__} max_depth={getattr(model, 'max_depth', None)}")


def run(mini_batch) -> pd.DataFrame:
    frames = []
    offset = 0
    for item in mini_batch:
        path = Path(str(item))
        data = pd.read_csv(path)
        # .to_numpy(), not the DataFrame: the estimator was fitted on an array
        # and carries no feature names, so handing it a named frame would work
        # but warn. Column ORDER is what matters, and it is the CSV's own.
        predictions = np.asarray(model.predict(data.to_numpy()))
        print(f"SCORING-RUN file={path.name} rows={len(data)} predictions={len(predictions)}")
        frames.append(
            pd.DataFrame(
                {
                    "row_index": range(offset, offset + len(predictions)),
                    "prediction": [int(v) for v in predictions],
                }
            )
        )
        offset += len(predictions)
    return pd.concat(frames, ignore_index=True)
