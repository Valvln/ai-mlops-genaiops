"""Read evaluations back out of Application Insights.

RUN THIS AS A SEPARATE INVOCATION FROM evaluate_call.py, for the reason
query_trace.py already gave one layer down: SC-002 asks whether a JUDGEMENT can
be retrieved after the fact, and a query sharing a process — or a scrollback —
with the evaluation it is "retrieving" answers an easier question. Everything
printed here comes from Log Analytics.

Three modes:

    --trace-id <id>                 what was concluded about one call
    --compare <ver-a> <ver-b>       which prompt revision scored higher
    --count-invocations             how many model calls this feature has spent

Usage:
    export LOG_ANALYTICS_WORKSPACE_ID="$(az monitor log-analytics workspace show \
        -g rg-ai300-foundry -n <law-name> --query customerId -o tsv)"
    uv run query_evaluations.py --trace-id <id>
    uv run query_evaluations.py --compare <ver-a> <ver-b> --metric groundedness
    uv run query_evaluations.py --count-invocations --since 1d
"""

import argparse
import os
import sys
from datetime import timedelta

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

WORKSPACE_VAR = "LOG_ANALYTICS_WORKSPACE_ID"

# Must match evaluate_call.py's SPAN_NAME and call_model.py's, respectively.
# Named rather than inlined for the same reason block 3 named its own: a
# mismatch here returns nothing while looking perfectly healthy.
EVAL_SPAN_NAME = "genaiops.eval"
CALL_SPAN_NAME = "genaiops.call"

# spec.md SC-006. Not a budget this script enforces — nothing here can stop a
# call — but the number the count is read against, so "well under the cap" is a
# comparison rather than an impression.
INVOCATION_CAP = 500


def eval_projection(alias: str = "") -> str:
    return f"""
    AppDependencies
    | where Name == '{EVAL_SPAN_NAME}'
    | project
        TimeGenerated,
        EvalTraceId = OperationId,
        EvaluatedTraceId = tostring(Properties['eval.evaluated_trace_id']),
        Metric = tostring(Properties['eval.metric']),
        PromptVersion = tostring(Properties['prompt.version']),
        Deployment = tostring(Properties['gen_ai.request.model']),
        JudgeModel = tostring(Properties['eval.judge_model']),
        Score = todouble(Properties['eval.score']),
        Threshold = todouble(Properties['eval.threshold']),
        Result = tostring(Properties['eval.result']),
        Reason = tostring(Properties['eval.reason'])
    {alias}
    """


def run_query(client: LogsQueryClient, workspace_id: str, query: str,
              since: timedelta) -> tuple[list[str], list[list]]:
    result = client.query_workspace(workspace_id, query, timespan=since)
    if result.status == LogsQueryStatus.FAILURE:
        # Surfaced, not swallowed: an unauthorised query and an empty window
        # look identical to a caller that only prints rows.
        raise RuntimeError(f"Query failed: {result.partial_error or 'unknown error'}")
    if not result.tables:
        return [], []
    return list(result.tables[0].columns), list(result.tables[0].rows)


def show_for_trace(client, workspace_id, trace_id, since) -> int:
    """What was concluded about one call, joined to the call itself."""
    query = f"""
    {eval_projection()}
    | where EvaluatedTraceId == '{trace_id}'
    | join kind=leftouter (
        AppDependencies
        | where Name == '{CALL_SPAN_NAME}'
        | project
            EvaluatedTraceId = OperationId,
            CallPromptFile = tostring(Properties['prompt.file']),
            CallResponse = tostring(Properties['gen_ai.response.content'])
      ) on EvaluatedTraceId
    | order by TimeGenerated desc
    """
    columns, rows = run_query(client, workspace_id, query, since)

    if not rows:
        # THE WHOLE OF FR-008. A call that was never scored has no record here,
        # and that is reported in words. Printing a row with a blank or zero
        # score would make "nobody checked" indistinguishable from "it scored
        # badly" — which is the one confusion this feature must not allow.
        print(f"No evaluation found for trace {trace_id}.")
        print("This call has NOT been scored. That is an absence of a record, "
              "not a score of zero and not a failing result.")
        print(f"(Searched the last {since}; ingestion lags an evaluation by "
              f"1-3 minutes.)")
        return 1

    for row in rows:
        record = dict(zip(columns, row))
        is_fixture = record["EvaluatedTraceId"] == "fixture"
        print(f"=== {record['TimeGenerated']} eval={record['EvalTraceId']}")
        if is_fixture:
            # An expected empty join, labelled as such. Without this the
            # missing genaiops.call row would read as a broken retrieval.
            print("    evaluated     : a committed fixture (no live call behind it)")
        else:
            print(f"    evaluated call: {record['EvaluatedTraceId']}")
            print(f"    prompt        : {record['CallPromptFile']} @ {record['PromptVersion']}")
            print(f"    deployment    : {record['Deployment']}")
        print(f"    metric        : {record['Metric']} (judge: {record['JudgeModel']})")
        print(f"    score         : {record['Score']} (threshold {record['Threshold']})")
        print(f"    result        : {record['Result']}")
        print(f"    reason        : {record['Reason']}")
        if not is_fixture and record["CallResponse"]:
            print(f"    response      : {record['CallResponse']}")
        print()

    print(f"{len(rows)} evaluation(s) retrieved from Log Analytics.")
    return 0


def compare(client, workspace_id, version_a, version_b, metric, since) -> int:
    """Which of two prompt revisions scored higher on one metric.

    SC-004 asks for the DIRECTION to be stated, not for two numbers left side
    by side for the reader to subtract. So this prints a conclusion.
    """
    query = f"""
    {eval_projection()}
    | where Metric == '{metric}'
    | where PromptVersion in ('{version_a}', '{version_b}')
    | summarize Score = avg(Score), Runs = count(), Result = any(Result)
        by PromptVersion
    """
    columns, rows = run_query(client, workspace_id, query, since)
    scores = {r[columns.index("PromptVersion")]: dict(zip(columns, r)) for r in rows}

    missing = [v for v in (version_a, version_b) if v not in scores]
    if missing:
        # Refused rather than half-answered. A comparison with one side absent
        # is not a weaker comparison, it is a different claim.
        print(f"No '{metric}' evaluation found for: {', '.join(missing)}")
        print(f"(Searched the last {since}.) Both revisions must be scored "
              f"before they can be compared.")
        return 1

    a, b = scores[version_a], scores[version_b]
    for label, rec in ((version_a, a), (version_b, b)):
        print(f"{label[:12]}  {metric}={rec['Score']:.2f}  "
              f"({rec['Runs']} run(s), {rec['Result']})")
    print()

    if a["Score"] == b["Score"]:
        print(f"No difference: both revisions scored {a['Score']:.2f} on "
              f"{metric}. The edit did not move this metric.")
    else:
        higher, lower = ((version_a, a), (version_b, b)) if a["Score"] > b["Score"] \
            else ((version_b, b), (version_a, a))
        print(f"{higher[0][:12]} scored HIGHER on {metric}: "
              f"{higher[1]['Score']:.2f} vs {lower[1]['Score']:.2f} "
              f"(+{higher[1]['Score'] - lower[1]['Score']:.2f}).")
    return 0


def count_invocations(client, workspace_id, since) -> int:
    """How many model calls this feature has actually spent, per SC-006.

    Counted FROM THE RECORDS THEMSELVES, never from a tally kept alongside
    them. A side count is a second source of truth that drifts the first time
    someone runs a script and forgets to update it — and the number it would
    drift toward is always the flattering one.

    Each genaiops.call is one invocation of the model under test; each
    genaiops.eval is one invocation of the judge. query_evaluations.py itself
    makes none — it only reads.
    """
    query = f"""
    AppDependencies
    | where Name in ('{CALL_SPAN_NAME}', '{EVAL_SPAN_NAME}')
    | summarize Invocations = count() by Name
    """
    columns, rows = run_query(client, workspace_id, query, since)
    counts = {r[columns.index("Name")]: r[columns.index("Invocations")] for r in rows}

    calls = counts.get(CALL_SPAN_NAME, 0)
    evals = counts.get(EVAL_SPAN_NAME, 0)
    total = calls + evals

    print(f"In the last {since}:")
    print(f"  {CALL_SPAN_NAME:16} {calls:>5}   (the model under test)")
    print(f"  {EVAL_SPAN_NAME:16} {evals:>5}   (the judge)")
    print(f"  {'TOTAL':16} {total:>5}   against a cap of {INVOCATION_CAP} (SC-006)")

    if total > INVOCATION_CAP:
        print(f"\nOVER THE CAP by {total - INVOCATION_CAP}. SC-006 is not met.",
              file=sys.stderr)
        return 1
    print(f"\nWithin the cap, with {INVOCATION_CAP - total} to spare.")
    return 0


def parse_since(value: str) -> timedelta:
    unit, amount = value[-1], int(value[:-1])
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise argparse.ArgumentTypeError(f"Use m, h or d — got {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--trace-id", help="Show evaluations of one call.")
    mode.add_argument("--compare", nargs=2, metavar=("VERSION_A", "VERSION_B"),
                      help="Compare two prompt revisions on one metric.")
    mode.add_argument("--count-invocations", action="store_true",
                      help="Count model invocations against SC-006's cap.")
    parser.add_argument("--metric", default="groundedness",
                        help="Metric for --compare (default groundedness).")
    parser.add_argument("--since", type=parse_since, default=timedelta(hours=2),
                        help="How far back to look (e.g. 30m, 2h, 1d). Default 2h.")
    args = parser.parse_args()

    workspace_id = os.environ.get(WORKSPACE_VAR)
    if not workspace_id:
        print(f"{WORKSPACE_VAR} is not set.", file=sys.stderr)
        return 2

    client = LogsQueryClient(DefaultAzureCredential())
    try:
        if args.trace_id:
            return show_for_trace(client, workspace_id, args.trace_id, args.since)
        if args.compare:
            return compare(client, workspace_id, args.compare[0], args.compare[1],
                           args.metric, args.since)
        return count_invocations(client, workspace_id, args.since)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
