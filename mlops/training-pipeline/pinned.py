"""The pinned values, in one place, imported by both sides of the comparison.

data-model.md section 2 names this module's contents as the single source of
truth for the hyperparameters and the split. The reason is specific: if
`train.py` and `baseline.py` each carried their own copy and the copies drifted,
the symptom would be a metric disagreement — indistinguishable from a real
tracking fault, and the one cause the comparison cannot diagnose. Every other
failure the comparison can detect, it can also explain.

`train.py` runs on the compute node with `code: .`, so this file is uploaded
alongside it and the remote job imports the same constants the local baseline
did.
"""

from __future__ import annotations

ESTIMATOR = "DecisionTreeClassifier"

# max_depth=4 is chosen so accuracy lands clear of both degenerate ends: not 1.0,
# which would make the comparison undiscriminating, and not near chance.
MAX_DEPTH = 4
RANDOM_STATE = 42

# Positional split - no RNG is involved, so there is no seed to agree about and
# no library version that can reinterpret it. The rows are already in random
# order by construction (see generate_data.py).
TRAIN_ROWS = 1500
TEST_ROWS = 500

SEED = 42

FEATURE_COLUMNS = [f"f{i}" for i in range(5)]
LABEL_COLUMN = "label"


def tracked_params(dataset_sha256: str) -> dict[str, object]:
    """The parameter set logged to the run and recorded in the baseline.

    Built here so that both sides log the same keys with the same spelling. A
    key present on one side and absent on the other is a comparison that quietly
    checks less than it claims to.
    """
    return {
        "seed": SEED,
        "estimator": ESTIMATOR,
        "max_depth": MAX_DEPTH,
        "random_state": RANDOM_STATE,
        "train_rows": TRAIN_ROWS,
        "test_rows": TEST_ROWS,
        "dataset_sha256": dataset_sha256,
    }
