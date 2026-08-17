"""Generate the synthetic training dataset for feature 005.

The dataset is generated once, locally, and uploaded. The job reads those bytes;
the local baseline reads the same local file. So the comparison the feature rests
on is between two reads of one artifact, and the fixed seed buys reproducibility
of the setup rather than validity of the comparison.

Two choices are deliberate and are the reason this file exists at all rather than
a one-line call into scikit-learn:

  * `numpy.random.default_rng` is used, not `sklearn.datasets.make_classification`.
    NumPy guarantees the `default_rng` stream across versions. scikit-learn makes
    no such promise about a dataset generator's internals, so a version bump could
    silently produce different bytes from the same seed.
  * Floats are written with fixed formatting, so the CSV bytes are a function of
    the seed and nothing else. Default repr would let a NumPy or pandas change
    alter the file without altering the data.

See specs/005-training-job-batch-endpoint/data-model.md section 1.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

# Pinned in data-model.md section 2, which is the single source of truth for
# these values. train.py and baseline.py read the same numbers.
SEED = 42
N_ROWS = 2000
N_FEATURES = 5
TRAIN_ROWS = 1500
TEST_ROWS = 500

# Fixed float formatting: six decimals is far more precision than a decision
# tree's split comparisons need, and it makes the byte count deterministic.
FLOAT_FORMAT = "{:.6f}"


def generate() -> tuple[np.ndarray, np.ndarray]:
    """Return (features, labels) from the pinned seed.

    The labelling rule is a closed form written out here rather than delegated,
    so that the procedure that produced the bytes is readable from this file
    alone. A linear score over three of the five features decides the class; the
    remaining two features are pure noise, which keeps the problem non-trivial
    without making it hard.
    """
    rng = np.random.default_rng(SEED)

    features = rng.normal(loc=0.0, scale=1.0, size=(N_ROWS, N_FEATURES))

    # f0, f1 and f2 carry signal; f3 and f4 do not. Noise is added to the score
    # so the classes overlap and accuracy lands clear of 1.0.
    score = 1.5 * features[:, 0] - 1.0 * features[:, 1] + 0.75 * features[:, 2]
    score += rng.normal(loc=0.0, scale=0.5, size=N_ROWS)

    # Threshold at the median, so the two classes are balanced by construction
    # and neither split can be starved of one of them.
    labels = (score > np.median(score)).astype(int)

    # Rows arrive in random order already, which is what makes the positional
    # split in baseline.py and train.py an unbiased one. No shuffle is applied
    # here: a shuffle would be a second consumer of the RNG stream, and the
    # order is not information the generator needs to add.
    return features, labels


def write_csv(path: Path, features: np.ndarray, labels: np.ndarray) -> None:
    header = ",".join(f"f{i}" for i in range(N_FEATURES)) + ",label\n"
    lines = [header]
    for row, label in zip(features, labels):
        cells = [FLOAT_FORMAT.format(value) for value in row]
        cells.append(str(int(label)))
        lines.append(",".join(cells) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


def validate_splits(labels: np.ndarray) -> None:
    """Refuse to write a dataset whose splits cannot discriminate.

    FR-003: if a split is dominated by one class, accuracy stops being a
    meaningful signal and the whole comparison loses its power to disagree.
    """
    for name, part in (
        ("train", labels[:TRAIN_ROWS]),
        ("test", labels[TRAIN_ROWS:]),
    ):
        if part.size == 0:
            raise SystemExit(f"split {name} is empty")
        for cls in (0, 1):
            share = float((part == cls).mean())
            if share < 0.30:
                raise SystemExit(
                    f"split {name}: class {cls} holds {share:.1%}, below the 30% floor"
                )
            print(f"split {name}: class {cls} = {share:.1%} ({int((part == cls).sum())} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "data" / "training.csv",
        help="Where to write the CSV",
    )
    args = parser.parse_args()

    features, labels = generate()
    validate_splits(labels)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output, features, labels)

    payload = args.output.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    print(f"path   {args.output}")
    print(f"bytes  {len(payload)}")
    print(f"rows   {N_ROWS}")
    print(f"sha256 {digest}")


if __name__ == "__main__":
    main()
