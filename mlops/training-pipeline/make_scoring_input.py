"""Build the scoring input for the batch endpoint, and refuse a useless one.

FR-022: the input must contain rows whose correct predictions **differ**. The
reason is specific and is not about coverage. If every row had the same class, a
deployment that ignored its input and returned a constant would score 100% on the
comparison — the check would pass while proving nothing about whether the
endpoint served the registered model.

Features only, no label column: the label is what the comparison holds back.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import modelling
import pinned

HERE = Path(__file__).parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "data" / "training.csv")
    parser.add_argument("--output", type=Path, default=HERE / "scoring-input" / "scoring.csv")
    parser.add_argument("--rows", type=int, default=100)
    args = parser.parse_args()

    frame = modelling.load_dataset(args.input)
    _, _, x_test, y_test = modelling.split(frame)

    # Taken from the head of the TEST split - rows the model never trained on.
    # Scoring rows the model was fitted on would still verify the serving path,
    # but it would be a needlessly weaker input for no saving.
    subset = x_test[: args.rows]

    # The model's own predictions decide whether the input discriminates. Using
    # the true labels here would be the wrong test: a constant-returning
    # deployment is caught by varied PREDICTIONS, not by varied ground truth.
    model = modelling.fit(*modelling.split(frame)[:2])
    predicted, _ = modelling.score(model, subset, y_test[: args.rows])

    classes = sorted({int(v) for v in predicted})
    if len(classes) < 2:
        raise SystemExit(
            f"scoring input predicts only class {classes} — a deployment that "
            "returned a constant would satisfy the comparison. Refusing to write it."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    header = ",".join(pinned.FEATURE_COLUMNS) + "\n"
    lines = [header]
    for row in subset:
        lines.append(",".join(f"{value:.6f}" for value in row) + "\n")
    args.output.write_text("".join(lines), encoding="utf-8")

    for cls in classes:
        count = int((predicted == cls).sum())
        print(f"predicted class {cls}: {count} rows ({count / len(predicted):.1%})")
    print(f"rows     {len(subset)}")
    print(f"sha256   {modelling.sha256_of(args.output)}")
    print(f"written  {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
