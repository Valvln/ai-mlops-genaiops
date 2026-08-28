"""Score the four runs against the labels and write the comparison table.

NO JUDGE MODEL, NO MODEL CALL, NO DEPLOYMENT NAME. DocumentRetrievalEvaluator is
arithmetic over human labels: it compares the order a method returned documents
in against the relevance a person assigned them. That is why block 4's F5 - a
default threshold promoting a confident fabrication - cannot recur in this form.
It also means every number here inherits the labels' bias and nothing else.

⚠️ THE LABEL RANGE IS DECLARED EXPLICITLY AND THAT IS LOAD-BEARING. The SDK
defaults to ground_truth_label_min=0, ground_truth_label_max=4 (verified against
1.18.3's signature), while Learn's own worked example passes 1 and 5. This
feature labels 0-3. `fidelity` weights labels over range(min + 1, max + 1), so a
range declared one point off does not raise - it silently reweights the metric.
Accepting the default here would produce a plausible number computed against a
grade nobody ever assigned.

RESULTS ARE READ FROM THE RETURN VALUE, IN-PROCESS. Not through the trace store:
block 4's F6 is closed as a known limitation, where spans are acknowledged with
HTTP 200 and then never become queryable, and its token counter reported 3 of
~13 calls - failing toward under-reporting. Anything routed through that store
inherits the loss, so nothing here is.

Usage:
    uv run score_retrieval.py --all --out results/comparison.md
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from azure.ai.evaluation import DocumentRetrievalEvaluator

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"
LABELS_PATH = HERE / "questions" / "labels.jsonl"
QUESTIONS_PATH = HERE / "questions" / "questions.jsonl"

LABEL_MIN, LABEL_MAX = 0, 3

METHODS = ("keyword", "vector", "hybrid", "hybrid_semantic")

# The pair FR-011 asks for: one ranking-shaped metric and one recall-shaped one.
# Reported first because a single metric cannot see the failure Learn's own
# example shows - ndcg@3 0.646 `pass` beside fidelity 0.019 `fail`, an excellent
# ranking over a result set that missed nearly everything.
HEADLINE = ("ndcg@3", "fidelity")
SECONDARY = ("xdcg@3", "top1_relevance", "top3_max_relevance")
SANITY = ("holes", "holes_ratio")


def load_labels() -> dict[str, dict[str, int]]:
    labels = defaultdict(dict)
    unlabelled = 0
    for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row["query_relevance_label"] is None:
            unlabelled += 1
            continue
        labels[row["question_id"]][row["chunk_id"]] = \
            int(row["query_relevance_label"])
    if unlabelled:
        # REFUSED, NOT DEGRADED. Scoring a partially labelled pool produces
        # holes that are an artefact of the sitting being unfinished, and
        # holes_ratio is the one number that must mean what it says.
        raise SystemExit(
            f"{unlabelled} pooled pairs still carry a null label. "
            f"Finish labelling questions/labels.jsonl, or re-pool.")
    return labels


def score_run(method: str, labels: dict[str, dict[str, int]]) -> dict:
    evaluator = DocumentRetrievalEvaluator(
        ground_truth_label_min=LABEL_MIN,
        ground_truth_label_max=LABEL_MAX,
    )
    per_question = {}
    for line in (RUNS_DIR / f"{method}.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        qid = row["question_id"]
        ground_truth = [
            {"document_id": cid, "query_relevance_label": label}
            for cid, label in labels.get(qid, {}).items()
        ]
        retrieved = [
            {"document_id": doc["chunk_id"], "relevance_score": doc["score"]}
            for doc in row["retrieved"]
        ]
        per_question[qid] = evaluator(
            retrieval_ground_truth=ground_truth,
            retrieved_documents=retrieved,
        )
    return per_question


def aggregate(per_question: dict) -> dict[str, float]:
    """Mean across questions, over every numeric metric the evaluator returned.

    Collected by inspection rather than by a hard-coded list so that a metric
    added by a future SDK version appears in the table instead of vanishing.
    The `*_passed` booleans are excluded here and reported separately: they are
    recorded and decide nothing.
    """
    sums = defaultdict(list)
    for result in per_question.values():
        for key, value in result.items():
            if isinstance(value, bool) or key.endswith("_result"):
                continue
            if isinstance(value, (int, float)):
                sums[key].append(float(value))
    return {k: statistics.fmean(v) for k, v in sorted(sums.items())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="results/comparison.md")
    args = ap.parse_args()

    labels = load_labels()
    questions = {q["question_id"]: q for q in
                 (json.loads(l) for l in
                  QUESTIONS_PATH.read_text(encoding="utf-8").splitlines() if l)}

    scored = {m: score_run(m, labels) for m in METHODS}
    means = {m: aggregate(scored[m]) for m in METHODS}

    every = sorted({k for m in means.values() for k in m})
    ordered = [k for k in (*HEADLINE, *SECONDARY, *SANITY) if k in every]
    ordered += [k for k in every if k not in ordered]

    rows = ["| Method | " + " | ".join(ordered) + " |",
            "| --- |" + " ---: |" * len(ordered)]
    for method in METHODS:
        cells = [f"{means[method].get(k, float('nan')):.3f}" for k in ordered]
        rows.append(f"| `{method}` | " + " | ".join(cells) + " |")

    holes = {m: means[m].get("holes_ratio", 0.0) for m in METHODS}
    worst = max(holes.values())

    out_path = HERE / args.out
    out_path.parent.mkdir(exist_ok=True)
    text = [
        "# Retrieval quality across four methods",
        "",
        f"{len(questions)} questions "
        f"({sum(1 for q in questions.values() if q['kind'] == 'control')} "
        f"control), {sum(len(v) for v in labels.values())} labelled pairs, "
        f"top 10, labels {LABEL_MIN}-{LABEL_MAX} declared explicitly.",
        "",
        "Scores are means across questions. **Raw retrieval scores are never "
        "compared across methods** - three incompatible ranges arrive under two "
        "property names, so the comparison is made only on these metrics, which "
        "are computed from ordering and labels and are scale-free.",
        "",
        *rows,
        "",
        f"**holes_ratio gate**: worst method {worst:.3f}. "
        + ("Comparison is reportable." if worst < 0.05 else
           "⚠️ HIGH - extend the pool and label again; a comparison over "
           "unjudged documents is declared unreliable, not published with a "
           "caveat (SC-003)."),
        "",
        "The evaluator's seven `*_passed` labels are recorded per question and "
        "decide nothing here (FR-010).",
        "",
        "## Per question, headline metrics",
        "",
        "| Question | kind | " + " | ".join(
            f"{m} ndcg@3" for m in METHODS) + " |",
        "| --- | --- |" + " ---: |" * len(METHODS),
    ]
    for qid in sorted(questions):
        cells = [f"{scored[m][qid].get('ndcg@3', float('nan')):.3f}"
                 for m in METHODS]
        text.append(f"| {qid} | {questions[qid]['kind']} | "
                    + " | ".join(cells) + " |")

    out_path.write_text("\n".join(text) + "\n", encoding="utf-8")

    print("\n".join(rows))
    print(f"\nholes_ratio worst: {worst:.3f}")
    print(f"wrote {out_path.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
