# Results: From a job that runs to a model that answers

**Feature**: 005 · Observed values, recorded as they were measured.

Predictions from [research.md](./research.md) are settled here — including the
ones that were wrong, which are kept as entries rather than quietly corrected.

---

## Phase 1 — 2026-08-16

### Local environment (T003)

Built with `uv sync` in `mlops/training-pipeline/`, pinned to match curated
environment `sklearn-1.5` version 52.

| Component | Resolved locally | Curated environment claims |
| --- | --- | --- |
| Python | 3.10.20 | 3.10 |
| scikit-learn | 1.5.2 | 1.5 (no patch published) |
| numpy | 1.26.4 | — |
| pandas | 2.3.3 | — |
| mlflow | 2.22.5 | — |
| Platform | macOS 15.3.2, x86_64 | Ubuntu 20.04 |

The platform row is the one that matters. Local metrics are computed on macOS
against a job running in an Ubuntu container, which is why the estimator was
chosen to avoid BLAS entirely ([research.md § R4](./research.md)). The remote
versions in the right-hand column are what the curated environment *claims*; the
`ENV-PROBE` banner reports what it actually installed, and the two are compared
at T018.

### The dataset (T005)

| Property | Value |
| --- | --- |
| Path | `mlops/training-pipeline/data/training.csv` |
| Bytes | 99,076 |
| Rows | 2,000 plus header |
| `sha256` | `9130b02593b6ce3fe84bbef7543b9397b96e05e36d131afa4b8daaf84bb60384` |

Class balance, against the 30% floor FR-003 sets:

| Split | Class 0 | Class 1 |
| --- | --- | --- |
| Train (rows 1–1500) | 49.5% (743) | 50.5% (757) |
| Test (rows 1501–2000) | 51.4% (257) | 48.6% (243) |

**Reproducibility checked, not assumed.** The generator was run a second time and
the output compared byte for byte against the first: identical, same digest. That
settles FR-001 locally — the recorded procedure reproduces the exact bytes, so
the seed and the fixed float formatting are doing what [research.md § R5](./research.md)
claimed for them.

### The local baseline (T007)

Written **2026-08-16 17:51:23 UTC**, before any job submission. The timestamp is
the evidence of ordering, and it is recorded here for that reason rather than for
completeness.

| Quantity | Value |
| --- | --- |
| `accuracy` | `0.854` |
| `f1` | `0.8488612836438924` |
| `predictions_sha256` | `495d5e534a0df9dcdcf499d09206b14e0398748b92068f32d542bfb0178f0163` |
| `dataset_sha256` | `9130b0…60384` — matches T005 |

Accuracy at 0.854 is what `max_depth: 4` was pinned to produce: clear of 1.0,
which would make the comparison undiscriminating, and clear of the ~0.5 a coin
would score. A criterion that cannot distinguish a working model from a broken
one has the same defect as one that cannot fail.
