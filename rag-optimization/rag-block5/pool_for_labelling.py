"""Pool the four runs into the set of (question, chunk) pairs that need a label.

WHY POOLING, AND WHY IT FORCES RETRIEVAL TO RUN BEFORE LABELLING. The obvious
order is to decide what is relevant first and then measure who found it. Do that
and every method surfaces documents nobody judged: the evaluator counts those as
`holes`, and `holes_ratio` then measures LABEL COVERAGE rather than retrieval
quality - while the comparison looks perfectly healthy. Standard IR practice is
the reverse: run the methods, take the union of what they returned, label that.
No method is then judged against a ground truth built without seeing it.

The union here is smaller than the sum of the runs, and by how much is itself a
result: four methods returning 220 rows each pool to 378 distinct pairs rather
than 880, which is the overlap between them stated as a number.

EXISTING LABELS ARE PRESERVED. T044 sends work back here when holes_ratio comes
out high - extend the pool, label again - and a re-pool that discarded the
previous sitting would make that loop unaffordable.

Usage:
    uv run pool_for_labelling.py
"""

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"
QUESTIONS_PATH = HERE / "questions" / "questions.jsonl"
LABELS_PATH = HERE / "questions" / "labels.jsonl"
WORKSHEET_PATH = HERE / "questions" / "worksheet.md"
CHUNKS_PATH = HERE / "chunks.jsonl"

# data-model.md § 6. Declared here as well as to the evaluator, because the two
# have to agree: fidelity weights labels over range(min + 1, max + 1), so a
# worksheet that invites a 4 would silently reweight the metric.
SCALE = {
    0: "not relevant",
    1: "marginally relevant - mentions the subject",
    2: "relevant - partially answers",
    3: "fully relevant - answers the question",
}


def main() -> int:
    questions = {q["question_id"]: q for q in
                 (json.loads(l) for l in
                  QUESTIONS_PATH.read_text(encoding="utf-8").splitlines() if l)}
    chunks = {c["chunk_id"]: c for c in
              (json.loads(l) for l in
               CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if l)}

    # Which methods found each pair, kept for the worksheet: a chunk that only
    # ONE method returned is where the disagreement between them lives, and it
    # is the pair most worth reading carefully.
    found_by = defaultdict(set)
    for run_path in sorted(RUNS_DIR.glob("*.jsonl")):
        if run_path.name == "query-embeddings.json":
            continue
        for line in run_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            for doc in row["retrieved"]:
                found_by[(row["question_id"], doc["chunk_id"])].add(row["method"])

    existing = {}
    if LABELS_PATH.is_file():
        for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            existing[(row["question_id"], row["chunk_id"])] = \
                row.get("query_relevance_label")

    pairs = sorted(found_by)
    kept = sum(1 for p in pairs if existing.get(p) is not None)

    with LABELS_PATH.open("w", encoding="utf-8") as fh:
        for qid, cid in pairs:
            fh.write(json.dumps({
                "question_id": qid,
                "chunk_id": cid,
                "query_relevance_label": existing.get((qid, cid)),
            }, ensure_ascii=False) + "\n")

    # The worksheet exists so labelling needs no second window and no query of
    # its own. Everything judged is judged from text in this file.
    lines = [
        "# Labelling worksheet",
        "",
        f"{len(pairs)} pairs pooled from {len(questions)} questions. "
        f"Fill `query_relevance_label` in `labels.jsonl`; this file is the "
        f"reading copy and is regenerated, never edited.",
        "",
        "| label | meaning |",
        "| ---: | --- |",
        *[f"| {k} | {v} |" for k, v in SCALE.items()],
        "",
        "⚠️ A `control` question's answer is genuinely absent from the corpus. "
        "Every one of its labels should be `0`; a chunk that looks tempting "
        "there is the defect the control exists to catch.",
        "",
        "⚠️ Where the prior in `questions.jsonl` and the label disagree, **the "
        "label wins**, and the correction is worth recording.",
        "",
    ]

    by_question = defaultdict(list)
    for qid, cid in pairs:
        by_question[qid].append(cid)

    for qid in sorted(by_question):
        question = questions[qid]
        prior = question["note"] or "-"
        lines += [
            "---",
            "",
            f"## {qid} · {question['kind']}",
            "",
            f"**{question['query']}**",
            "",
            f"prior: `{prior}` · {len(by_question[qid])} pooled chunks",
            "",
        ]
        for cid in by_question[qid]:
            chunk = chunks[cid]
            methods = ", ".join(sorted(found_by[(qid, cid)]))
            body = chunk["content"].strip().replace("\n", " ")
            lines += [
                f"### `{cid}`  __label: ___",
                f"*{chunk['note']} › {chunk['heading']}* · found by **{methods}**",
                "",
                f"> {body[:700]}{'…' if len(body) > 700 else ''}",
                "",
            ]

    WORKSHEET_PATH.write_text("\n".join(lines), encoding="utf-8")

    only_one = sum(1 for p in pairs if len(found_by[p]) == 1)
    all_four = sum(1 for p in pairs if len(found_by[p]) == 4)
    print(f"pooled {len(pairs)} pairs from {len(questions)} questions")
    print(f"  {all_four} returned by all four methods, "
          f"{only_one} by exactly one")
    print(f"  {kept} existing labels preserved, "
          f"{len(pairs) - kept} still to label")
    print(f"wrote {LABELS_PATH.name} and {WORKSHEET_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
