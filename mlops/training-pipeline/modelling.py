"""The load, split, fit and score path — shared by both sides of the comparison.

`pinned.py` removes the risk that the two scripts disagree about a *value*. This
module removes the risk that they disagree about a *step*: reading the columns in
a different order, splitting before rather than after dropping the label, scoring
on the wrong split. Those would all present exactly as a metric disagreement,
which is the symptom the comparison is meant to attribute to the job.

What remains different between the two sides after this is what the feature
actually tests: a Linux node inside a curated container versus macOS, and a
tracked record versus a local one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.tree import DecisionTreeClassifier

import pinned


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    expected = pinned.FEATURE_COLUMNS + [pinned.LABEL_COLUMN]
    if list(frame.columns) != expected:
        raise ValueError(f"columns {list(frame.columns)} != expected {expected}")
    return frame


def split(frame: pd.DataFrame):
    """Positional split. No RNG, so there is no seed to agree about."""
    if len(frame) != pinned.TRAIN_ROWS + pinned.TEST_ROWS:
        raise ValueError(
            f"{len(frame)} rows, expected {pinned.TRAIN_ROWS + pinned.TEST_ROWS}"
        )
    train = frame.iloc[: pinned.TRAIN_ROWS]
    test = frame.iloc[pinned.TRAIN_ROWS :]

    x_train = train[pinned.FEATURE_COLUMNS].to_numpy()
    y_train = train[pinned.LABEL_COLUMN].to_numpy()
    x_test = test[pinned.FEATURE_COLUMNS].to_numpy()
    y_test = test[pinned.LABEL_COLUMN].to_numpy()
    return x_train, y_train, x_test, y_test


def fit(x_train: np.ndarray, y_train: np.ndarray) -> DecisionTreeClassifier:
    model = DecisionTreeClassifier(
        max_depth=pinned.MAX_DEPTH,
        random_state=pinned.RANDOM_STATE,
    )
    model.fit(x_train, y_train)
    return model


def score(model, x_test: np.ndarray, y_test: np.ndarray):
    """Metrics on the TEST split only.

    Computing them on the training split is a failure mode that yields entirely
    plausible numbers, which is why the baseline comparison exists rather than a
    reasonableness check on the values.
    """
    predictions = model.predict(x_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "f1": float(f1_score(y_test, predictions)),
    }
    return predictions, metrics


def predictions_digest(predictions: np.ndarray) -> str:
    """Digest of the prediction vector, in row order.

    Rendered as a canonical comma-joined string of integers rather than hashing
    raw array bytes: the raw buffer carries dtype and endianness, which are
    platform properties and not predictions. Hashing those would make the digest
    fail across platforms for a reason that has nothing to do with the model.
    """
    canonical = ",".join(str(int(value)) for value in predictions)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
