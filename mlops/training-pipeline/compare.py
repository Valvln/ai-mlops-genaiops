"""Compare the tracked run against the baseline recorded before it ran.

**This is the criterion.** A run appearing in the workspace proves a job ran; it
says nothing about whether the numbers are the right numbers. The only artifact
capable of contradicting a tracked result is one computed independently, before
the job, and that is `baseline.json`.

Two sources for the run are supported, and they answer different questions:

  * `--run-log` reads the METRIC and DATA-PROBE blocks out of the job's
    `user_logs/std_log.txt`. Available even if the tracking store cannot be
    read — which matters on the one run where reachability of the tracking
    store is the thing under test.
  * `--run-id` reads params, metrics and tags back out of the WORKSPACE through
    MLflow. This is the source that settles FR-012, because a record that can be
    read after the compute node is gone is what distinguishes real tracking from
    a local `mlruns/` directory that died at scale-down.

Given both, the two are also checked against each other. A disagreement there
would mean the log and the tracking store describe different runs.

The tolerance is not a negotiating position (FR-016). The estimator was chosen
so that exact agreement is expected (research.md R4); widening the tolerance
after a disagreement throws away the discriminating power that choice bought.
Record the disagreement and investigate it.

Contract: specs/005-training-job-batch-endpoint/contracts/training-run.md section 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

METRIC_TOLERANCE = 1e-9

# Params compared key by key. `input_mount_path` is deliberately excluded: it is
# a property of where the data store mounted, not of the experiment, and it has
# no counterpart in a baseline computed on a local path.
COMPARED_PARAMS = [
    "seed",
    "estimator",
    "max_depth",
    "random_state",
    "train_rows",
    "test_rows",
    "dataset_sha256",
]


class Mismatch(list):
    def add(self, what: str, expected, observed) -> None:
        self.append(f"{what}: baseline={expected!r} run={observed!r}")


def parse_log(path: Path) -> dict:
    """Pull the greppable blocks out of the job log.

    The log is the interface precisely because it is greppable — see the
    contract's opening note on why a UI reading is neither reproducible nor
    available to a script.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    found: dict[str, str] = {}
    for prefix in ("ENV-PROBE", "DATA-PROBE", "METRIC"):
        for match in re.finditer(rf"^{prefix} (\w+)=(.*)$", text, re.MULTILINE):
            found[match.group(1)] = match.group(2).strip()
    if not found:
        raise SystemExit(f"no ENV-PROBE / DATA-PROBE / METRIC lines found in {path}")
    return found


def read_run_from_workspace(run_id: str, tracking_uri: str) -> dict:
    """Read the run back out of the workspace, after the node is gone."""
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    run = mlflow.get_run(run_id)
    return {
        "params": dict(run.data.params),
        "metrics": dict(run.data.metrics),
        "tags": dict(run.data.tags),
        "status": run.info.status,
    }


def compare_params(baseline: dict, observed: dict, mismatches: Mismatch) -> None:
    for key in COMPARED_PARAMS:
        if key not in observed:
            mismatches.add(f"param {key}", baseline["params"].get(key), "MISSING")
            continue
        # MLflow returns every param as a string. Compare on the string
        # rendering of the baseline value rather than coercing the observed one,
        # which would let "4.0" quietly satisfy an expected 4.
        expected = str(baseline["params"][key])
        if expected != str(observed[key]):
            mismatches.add(f"param {key}", expected, observed[key])


def compare_metrics(baseline: dict, observed: dict, mismatches: Mismatch) -> None:
    for key in ("accuracy", "f1"):
        if key not in observed:
            mismatches.add(f"metric {key}", baseline["metrics"][key], "MISSING")
            continue
        expected = float(baseline["metrics"][key])
        actual = float(observed[key])
        if abs(expected - actual) > METRIC_TOLERANCE:
            mismatches.add(
                f"metric {key} (delta {abs(expected - actual):.3e} > {METRIC_TOLERANCE:g})",
                expected,
                actual,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path(__file__).parent / "baseline.json")
    parser.add_argument("--run-log", type=Path, help="Downloaded user_logs/std_log.txt")
    parser.add_argument("--run-id", help="MLflow run id, read back from the workspace")
    parser.add_argument("--tracking-uri", help="azureml:// tracking URI for --run-id")
    args = parser.parse_args()

    if not args.run_log and not args.run_id:
        raise SystemExit("give at least one of --run-log or --run-id")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    mismatches = Mismatch()
    checks: list[str] = []

    log = parse_log(args.run_log) if args.run_log else None
    if log:
        checks.append(f"log      {args.run_log}")
        # The digest is what stops the whole verification passing on data the
        # job supplied to itself (FR-004).
        if log.get("sha256") != baseline["dataset_sha256"]:
            mismatches.add("log dataset sha256", baseline["dataset_sha256"], log.get("sha256"))
        if log.get("predictions_sha256") != baseline["predictions_sha256"]:
            mismatches.add(
                "log predictions sha256",
                baseline["predictions_sha256"],
                log.get("predictions_sha256"),
            )
        compare_metrics(baseline, {k: log[k] for k in ("accuracy", "f1") if k in log}, mismatches)

    run = None
    if args.run_id:
        if not args.tracking_uri:
            raise SystemExit("--run-id needs --tracking-uri")
        run = read_run_from_workspace(args.run_id, args.tracking_uri)
        checks.append(f"run      {args.run_id} (status {run['status']}) read from the workspace")
        compare_params(baseline, run["params"], mismatches)
        compare_metrics(baseline, run["metrics"], mismatches)
        tracked_digest = run["tags"].get("predictions_sha256")
        if tracked_digest != baseline["predictions_sha256"]:
            mismatches.add(
                "tracked predictions sha256", baseline["predictions_sha256"], tracked_digest
            )

    if log and run:
        # Cross-check: the log and the tracking store must describe one run.
        for key in ("accuracy", "f1"):
            if key in log and key in run["metrics"]:
                if abs(float(log[key]) - float(run["metrics"][key])) > METRIC_TOLERANCE:
                    mismatches.add(
                        f"log vs tracked {key}", float(log[key]), float(run["metrics"][key])
                    )
        checks.append("cross     log METRIC block against the tracked run")

    print("COMPARED")
    for line in checks:
        print(f"  {line}")
    print(f"  baseline {args.baseline} (computed {baseline['computed_at']})")

    if mismatches:
        print(f"\nDISAGREEMENT — {len(mismatches)} finding(s):", file=sys.stderr)
        for line in mismatches:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nDo NOT widen the tolerance (FR-016). Look first at the "
            "scikit-learn patch version in the ENV-PROBE banner, then at the "
            "DATA-PROBE digest.",
            file=sys.stderr,
        )
        return 1

    print("\nAGREEMENT — params, metrics and the prediction vector all match the baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
