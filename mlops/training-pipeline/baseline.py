"""Compute the local baseline, before the job is submitted.

This is the only artifact in feature 005 capable of contradicting a tracked
result. Everything else the feature produces is downstream of the job; this is
computed independently, on the author's machine, from the same bytes.

**Order is load-bearing.** The baseline must be written before the job runs. A
baseline computed afterwards proves only that the same code run twice agrees
with itself, and the file's own modification time is the evidence of ordering.

See specs/005-training-job-batch-endpoint/data-model.md section 2.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

import modelling
import pinned

HERE = Path(__file__).parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "data" / "training.csv")
    parser.add_argument("--output", type=Path, default=HERE / "baseline.json")
    args = parser.parse_args()

    digest = modelling.sha256_of(args.input)
    frame = modelling.load_dataset(args.input)
    x_train, y_train, x_test, y_test = modelling.split(frame)

    model = modelling.fit(x_train, y_train)
    predictions, metrics = modelling.score(model, x_test, y_test)

    baseline = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(args.input.name),
        "dataset_sha256": digest,
        "dataset_rows": int(len(frame)),
        "params": pinned.tracked_params(digest),
        "metrics": metrics,
        # The vector itself, not only its digest. The digest is what the
        # comparison checks; the vector is what makes a disagreement
        # investigable without recomputing anything.
        "predictions": [int(value) for value in predictions],
        "predictions_sha256": modelling.predictions_digest(predictions),
        "library_versions": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }

    args.output.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    print(f"dataset_sha256     {digest}")
    print(f"rows               {baseline['dataset_rows']}")
    print(f"accuracy           {metrics['accuracy']!r}")
    print(f"f1                 {metrics['f1']!r}")
    print(f"predictions_sha256 {baseline['predictions_sha256']}")
    print(f"written            {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
