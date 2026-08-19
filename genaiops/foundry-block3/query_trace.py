"""Read past calls back out of Application Insights.

RUN THIS AS A SEPARATE INVOCATION FROM call_model.py — ideally from a terminal
that never saw the call happen. That is not a stylistic preference: SC-004
asks whether a record can be retrieved after the fact, and a query that shares
a process (or a scrollback) with the call it is "retrieving" answers a
different, easier question. Everything printed here comes from the Log
Analytics workspace.

The query searches by TIME WINDOW, not by a trace id handed over from the
caller, for the same reason. Pass --trace-id only to confirm that a specific
call is among what was found.

Usage:
    export LOG_ANALYTICS_WORKSPACE_ID="$(az monitor log-analytics workspace show \
        -g rg-ai300-foundry -n <law-name> --query customerId -o tsv)"
    uv run query_trace.py [--since 30m] [--trace-id <id>]
"""

import argparse
import os
import sys
from datetime import timedelta

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

WORKSPACE_VAR = "LOG_ANALYTICS_WORKSPACE_ID"

# Must match call_model.py's SPAN_NAME. Duplicated across two files because
# they are two programs, not one — but a mismatch here is the single most
# likely way this retrieval returns nothing while looking healthy, so it is
# named rather than inlined.
SPAN_NAME = "genaiops.call"

# Custom span attributes land in the Properties column of AppDependencies for
# a workspace-based Application Insights component. Internal (non-HTTP) spans
# are recorded as dependencies, not as AppTraces — which is why this queries
# the table it does.
QUERY = f"""
AppDependencies
| where Name == '{SPAN_NAME}'
| project
    TimeGenerated,
    TraceId = OperationId,
    PromptFile = tostring(Properties['prompt.file']),
    PromptVersion = tostring(Properties['prompt.version']),
    Deployment = tostring(Properties['gen_ai.request.model']),
    ResponseModel = tostring(Properties['gen_ai.response.model']),
    InputTokens = tostring(Properties['gen_ai.usage.input_tokens']),
    OutputTokens = tostring(Properties['gen_ai.usage.output_tokens']),
    Response = tostring(Properties['gen_ai.response.content'])
| order by TimeGenerated desc
"""


def parse_since(value: str) -> timedelta:
    unit = value[-1]
    amount = int(value[:-1])
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise argparse.ArgumentTypeError(f"Use m, h or d — got {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=parse_since, default=timedelta(minutes=30),
                        help="How far back to look (e.g. 10m, 2h, 1d). Default 30m.")
    parser.add_argument("--trace-id", default=None,
                        help="Optional: highlight one trace among the results.")
    args = parser.parse_args()

    workspace_id = os.environ.get(WORKSPACE_VAR)
    if not workspace_id:
        print(f"{WORKSPACE_VAR} is not set.", file=sys.stderr)
        return 2

    client = LogsQueryClient(DefaultAzureCredential())
    result = client.query_workspace(workspace_id, QUERY, timespan=args.since)

    if result.status == LogsQueryStatus.FAILURE:
        # Surfaced, not swallowed. An unauthorised query and an empty window
        # look identical to a caller that only prints rows.
        print(f"Query failed: {result.partial_error or 'unknown error'}",
              file=sys.stderr)
        return 1

    rows = list(result.tables[0].rows) if result.tables else []
    if not rows:
        # AN EMPTY RESULT IS NOT A PROVEN ABSENCE, and saying so is the point.
        # Application Insights ingestion lags a call by roughly one to three
        # minutes; this project has already once read "no rows" as "it didn't
        # happen" (infra/DEPLOY.md § 4, on Cost Management).
        print(f"No '{SPAN_NAME}' spans in the last {args.since}.")
        print("Ingestion lags a call by 1-3 minutes — widen --since or wait "
              "before concluding the call was not traced.")
        return 1

    columns = result.tables[0].columns
    for row in rows:
        record = dict(zip(columns, row))
        marker = " <-- requested" if args.trace_id and record["TraceId"] == args.trace_id else ""
        print(f"=== {record['TimeGenerated']} trace={record['TraceId']}{marker}")
        print(f"    prompt        : {record['PromptFile']} @ {record['PromptVersion']}")
        print(f"    deployment    : {record['Deployment']} (answered by {record['ResponseModel']})")
        print(f"    tokens        : in={record['InputTokens']} out={record['OutputTokens']}")
        print(f"    response      : {record['Response']}")
        print()

    print(f"{len(rows)} record(s) retrieved from Log Analytics.")

    if args.trace_id and not any(dict(zip(columns, r))["TraceId"] == args.trace_id for r in rows):
        print(f"WARNING: {args.trace_id} was not among them.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
