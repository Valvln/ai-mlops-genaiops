"""The training job for feature 005 — probes, asserts, trains, tracks, logs.

All of it in **one** cluster activation. Billing runs from node allocation rather
than from script start (compute-cost-model.md section 7.2), so a separate probe
job to answer the MLflow question would cost roughly what the real job costs, to
learn something this script reports for free in its first three lines.

The log is the interface. Everything the verification needs is greppable from
`user_logs/std_log.txt`, because the author holds no data-plane role on this
workspace and reads job logs with the account key rather than through `az ml job
download` — established in feature 004.

Contract: specs/005-training-job-batch-endpoint/contracts/training-run.md

Exit codes:
    0  trained, tracked, every probe satisfied
    2  input not mounted, or mounted as the wrong type
    3  tracking URI is not azureml-backed — refused to train
    4  data digest disagrees with the expected value passed in
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import sklearn

import modelling
import pinned

EXIT_INPUT = 2
EXIT_TRACKING = 3
EXIT_DIGEST = 4


def _version(module_name: str) -> str:
    """Report a version without letting a missing package end the probe.

    ABSENT is a result. The banner exists to record what the curated environment
    actually contains, and an import error here would destroy the record instead
    of writing it.
    """
    try:
        module = __import__(module_name)
    except ImportError:
        return "ABSENT"
    return getattr(module, "__version__", "PRESENT-NO-VERSION")


def environment_probe() -> str:
    """Emit the ENV-PROBE block and return the resolved tracking URI.

    Settles research.md R1 and R2 at no extra cost. Both `MLFLOW_TRACKING_URI`
    and `mlflow.get_tracking_uri()` are reported because they are not necessarily
    the same thing: the resolved value is what MLflow will actually write to.
    """
    resolved = mlflow.get_tracking_uri()

    print("ENV-PROBE-BEGIN", flush=True)
    print(f"ENV-PROBE mlflow_tracking_uri_env={os.environ.get('MLFLOW_TRACKING_URI', 'ABSENT')}")
    print(f"ENV-PROBE mlflow_resolved_uri={resolved}")
    print(f"ENV-PROBE mlflow_version={_version('mlflow')}")
    print(f"ENV-PROBE azureml_mlflow_version={_version('azureml.mlflow')}")
    print(f"ENV-PROBE sklearn_version={sklearn.__version__}")
    print(f"ENV-PROBE numpy_version={np.__version__}")
    print(f"ENV-PROBE pandas_version={pd.__version__}")
    print(f"ENV-PROBE python_version={sys.version.split()[0]}")
    print(f"ENV-PROBE platform={platform.platform()}")
    print("ENV-PROBE-END", flush=True)

    return resolved


def assert_tracking(resolved: str) -> None:
    """Refuse to train if MLflow is not pointed at the workspace.

    This is the load-bearing check of the whole job. MLflow does not fail when
    unconfigured: it writes to a local `mlruns/` directory on the node, the
    script exits zero, and every metric is destroyed with the node at
    scale-down. A green run that tracked nothing is the exact defect shape this
    repository keeps producing, and without this assertion the job cannot fail on
    the axis being tested.

    Both answers are acceptable results. What is not acceptable is not knowing.
    """
    if not resolved.startswith("azureml"):
        print(
            "TRACKING-REFUSED resolved URI is not azureml-backed: "
            f"{resolved!r}. Refusing to train — metrics would be written to a "
            "local mlruns/ directory and destroyed at scale-down.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(EXIT_TRACKING)
    print(f"TRACKING-OK resolved URI is azureml-backed: {resolved}", flush=True)


def data_probe(input_path: Path, expected_sha256: str) -> pd.DataFrame:
    """Emit the DATA-PROBE block and prove the job read the expected bytes.

    This is what stops the entire verification from passing on data the job
    supplied to itself (FR-004). It reuses feature 004's mechanism unchanged:
    that job proved a datastore read with a checksum for the same reason.
    """
    if not input_path.is_file():
        print(
            f"INPUT-MISSING {input_path} is not a file. Mounted as the wrong "
            "type, or not mounted at all.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(EXIT_INPUT)

    payload = input_path.read_bytes()
    digest = modelling.sha256_of(input_path)
    frame = modelling.load_dataset(input_path)

    print("DATA-PROBE-BEGIN", flush=True)
    print(f"DATA-PROBE path={input_path}")
    print(f"DATA-PROBE bytes={len(payload)}")
    print(f"DATA-PROBE sha256={digest}")
    print(f"DATA-PROBE rows={len(frame)}")
    print(f"DATA-PROBE train_rows={pinned.TRAIN_ROWS}")
    print(f"DATA-PROBE test_rows={pinned.TEST_ROWS}")
    print("DATA-PROBE-END", flush=True)

    if expected_sha256 and digest != expected_sha256:
        print(
            f"DIGEST-MISMATCH read {digest}, expected {expected_sha256}. The "
            "job did not receive the bytes the baseline was computed on.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(EXIT_DIGEST)

    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--expected-sha256",
        default="",
        help="Digest recorded locally before upload. The job fails rather than "
        "trains if the bytes it received do not match.",
    )
    args = parser.parse_args()

    resolved = environment_probe()
    assert_tracking(resolved)

    frame = data_probe(args.input, args.expected_sha256)
    digest = modelling.sha256_of(args.input)

    x_train, y_train, x_test, y_test = modelling.split(frame)
    model = modelling.fit(x_train, y_train)
    predictions, metrics = modelling.score(model, x_test, y_test)
    prediction_digest = modelling.predictions_digest(predictions)

    params = pinned.tracked_params(digest)
    for key, value in params.items():
        mlflow.log_param(key, value)
    mlflow.log_param("input_mount_path", str(args.input))

    for key, value in metrics.items():
        mlflow.log_metric(key, value)

    # Tags rather than params for the environment banner: params are the
    # experiment's inputs, and a library version is provenance. Recorded on the
    # run so the version comparison survives without the log file.
    mlflow.set_tags(
        {
            "resolved_tracking_uri": resolved,
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "python_version": sys.version.split()[0],
            "predictions_sha256": prediction_digest,
        }
    )

    # MLflow format, not a file upload. Phase 2 deploys this with no scoring
    # script, which Azure ML can only derive from a model that carries its own
    # metadata. A generic file upload would still satisfy "an artifact exists"
    # while quietly forcing a scoring script the next day (research.md R8).
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        input_example=x_test[:5],
    )

    print("METRIC-BEGIN", flush=True)
    print(f"METRIC accuracy={metrics['accuracy']!r}")
    print(f"METRIC f1={metrics['f1']!r}")
    print(f"METRIC predictions_sha256={prediction_digest}")
    print("METRIC-END", flush=True)

    print("TRAIN-COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
