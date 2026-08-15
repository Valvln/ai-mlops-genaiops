"""Prove that a job running on the cluster can read through the datastore.

This script trains nothing and is not meant to. It exists to settle one
question: did the bytes of a known file actually reach a node of the compute
cluster, having been addressed through an Azure ML datastore that carries no
credential?

The output is deliberately derived from the file's contents. A job that starts,
logs, and exits zero would satisfy a naive check while proving nothing about
data access, so this prints a digest that cannot be produced without having read
the bytes. The expected values are recorded in README.md, before this script
ever ran.

Standard library only: the curated environment this runs in is not ours to add
packages to, and nothing here needs more.
"""

import argparse
import hashlib
import pathlib
import sys


def summarise(path: pathlib.Path) -> dict[str, object]:
    """Read the file once and derive everything from that single read."""
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        # Rows excluding the header. Counted from the bytes just read rather
        # than by reopening the file, so every figure below describes the same
        # read.
        "rows": max(len(data.decode("utf-8").splitlines()) - 1, 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Path the job mounts the datastore file at. Supplied by job.yml.",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.input)

    # An input that arrives as a directory is not a failure of data access - it
    # is a different input type than intended. Say which, rather than dying on
    # an IsADirectoryError that reads like a permissions problem.
    if path.is_dir():
        candidates = sorted(p for p in path.iterdir() if p.is_file())
        print(f"INPUT IS A DIRECTORY, containing: {[p.name for p in candidates]}")
        if len(candidates) != 1:
            print("FAIL: expected exactly one file. Check the input type in job.yml.")
            return 2
        path = candidates[0]

    if not path.exists():
        print(f"FAIL: nothing at {path}. The input was not mounted.")
        return 2

    summary = summarise(path)

    # Prefixed so the values are greppable in the job log, which is where they
    # will actually be read from.
    print("DATASTORE-CHECK-BEGIN")
    for key, value in summary.items():
        print(f"DATASTORE-CHECK {key}={value}")
    print("DATASTORE-CHECK-END")

    return 0


if __name__ == "__main__":
    sys.exit(main())
