# Retrieval quality across four methods

22 questions (2 control), 378 labelled pairs, top 10, labels 0-3 declared explicitly.

Scores are means across questions. **Raw retrieval scores are never compared across methods** - three incompatible ranges arrive under two property names, so the comparison is made only on these metrics, which are computed from ordering and labels and are scale-free.

| Method | ndcg@3 | fidelity | xdcg@3 | top1_relevance | top3_max_relevance | holes | holes_ratio | total_ground_truth_documents | total_retrieved_documents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `keyword` | 0.472 | 0.646 | 32.073 | 1.636 | 2.182 | 0.000 | 0.000 | 17.182 | 10.000 |
| `vector` | 0.579 | 0.816 | 39.402 | 1.818 | 2.364 | 0.000 | 0.000 | 17.182 | 10.000 |
| `hybrid` | 0.545 | 0.816 | 37.314 | 1.682 | 2.318 | 0.000 | 0.000 | 17.182 | 10.000 |
| `hybrid_semantic` | 0.601 | 0.843 | 39.865 | 1.773 | 2.318 | 0.000 | 0.000 | 17.182 | 10.000 |

**holes_ratio gate**: worst method 0.000. Comparison is reportable.

The evaluator's seven `*_passed` labels are recorded per question and decide nothing here (FR-010).

## Per question, headline metrics

| Question | kind | keyword ndcg@3 | vector ndcg@3 | hybrid ndcg@3 | hybrid_semantic ndcg@3 |
| --- | --- | ---: | ---: | ---: | ---: |
| q01 | answerable | 0.096 | 0.048 | 0.471 | 0.182 |
| q02 | answerable | 0.591 | 0.458 | 0.458 | 0.862 |
| q03 | answerable | 0.418 | 0.397 | 0.320 | 0.116 |
| q04 | answerable | 0.803 | 1.000 | 1.000 | 1.000 |
| q05 | answerable | 0.782 | 0.879 | 0.782 | 0.904 |
| q06 | answerable | 0.688 | 0.552 | 0.613 | 0.845 |
| q07 | answerable | 0.734 | 0.397 | 0.762 | 0.666 |
| q08 | answerable | 0.160 | 0.143 | 0.143 | 0.076 |
| q09 | answerable | 0.542 | 0.923 | 0.658 | 0.727 |
| q10 | answerable | 0.126 | 0.458 | 0.165 | 0.242 |
| q11 | answerable | 0.790 | 1.000 | 1.000 | 0.736 |
| q12 | answerable | 0.157 | 0.666 | 0.569 | 0.144 |
| q13 | answerable | 0.866 | 0.866 | 0.866 | 0.972 |
| q14 | answerable | 0.096 | 0.904 | 0.301 | 0.722 |
| q15 | answerable | 0.866 | 0.866 | 0.866 | 0.866 |
| q16 | answerable | 0.337 | 0.521 | 0.473 | 0.301 |
| q17 | answerable | 0.227 | 0.440 | 0.227 | 0.866 |
| q18 | answerable | 0.922 | 0.922 | 0.922 | 1.000 |
| q19 | answerable | 0.263 | 0.165 | 0.242 | 0.923 |
| q20 | answerable | 0.337 | 0.397 | 0.433 | 0.494 |
| q21 | control | 0.579 | 0.726 | 0.726 | 0.579 |
| q22 | control | 0.000 | 0.000 | 0.000 | 0.000 |
