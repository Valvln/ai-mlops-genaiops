"""Score one model response with an evaluator, and record the score as a trace.

Block 3 proved a call could be retrieved after the fact. This is the same claim
one layer up: the JUDGEMENT about a call has to be retrievable too, by a
separate process, or "we evaluated it" is just something a terminal said once.
So an evaluation is a span (`genaiops.eval`), not a printout —
query_evaluations.py reads it back from Log Analytics, and that separation is
what makes SC-002 a test rather than a restatement.

Two ways in, mutually exclusive:

    --trace-id <id>    score a real call block 3's call_model.py already made
    --fixture <path>   score a hand-authored query/context/response triple

The fixture path exists because User Story 3 needs a response that FAILS
groundedness, and asking a live model to hallucinate on demand is neither
reliable nor free (research.md § R7). A committed JSON file fails the same way
every time, and costs one judge call instead of an unbounded number of attempts
to provoke a bad answer.

Usage:
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    export APPLICATIONINSIGHTS_CONNECTION_STRING="$(az monitor app-insights component show \
        -g rg-ai300-foundry -a <appi-name> --query connectionString -o tsv)"
    export LOG_ANALYTICS_WORKSPACE_ID="$(az monitor log-analytics workspace show \
        -g rg-ai300-foundry -n <law-name> --query customerId -o tsv)"

    uv run evaluate_call.py --trace-id <id> --metric relevance
    uv run evaluate_call.py --fixture fixtures/unsupported_claim.json --metric groundedness
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import prompty
from azure.ai.evaluation import (
    AzureOpenAIModelConfiguration,
    GroundednessEvaluator,
    RelevanceEvaluator,
)
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from opentelemetry import trace

ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"
CONNECTION_STRING_VAR = "APPLICATIONINSIGHTS_CONNECTION_STRING"
WORKSPACE_VAR = "LOG_ANALYTICS_WORKSPACE_ID"

# Pinned for the same reason block 3 pins its own: an unpinned data-plane API
# version is a dependency that changes without a commit.
API_VERSION = "2024-10-21"

# The span this feature WRITES. query_evaluations.py reads it.
SPAN_NAME = "genaiops.eval"

# The span block 3 writes and this feature READS. Duplicated from
# call_model.py rather than imported — they are two programs in two uv
# projects — but named here rather than inlined, because a mismatch is the
# quietest way for this whole script to find nothing while looking healthy.
CALL_SPAN_NAME = "genaiops.call"

# The judge. research.md § R5: the same deployment being evaluated, rather than
# a second one, because this project's whole posture is one deployment at a
# time — and because a second deployment would be a second thing to remember to
# delete. This is the choice most likely to need revisiting: if the judge's
# output stops parsing, that is the finding, not something to paper over.
JUDGE_DEPLOYMENT = "gpt-4.1-mini"

# Where to look for the prompt file a genaiops.call span names. Block 4's own
# prompts first, then block 3's — this feature reads block 3's folder but never
# writes to it (plan.md, Project Structure).
PROMPT_SEARCH_DIRS = [
    Path(__file__).parent / "prompts",
    Path(__file__).parent.parent.parent / "genaiops" / "foundry-block3" / "prompts",
]

EVALUATORS = {
    "groundedness": GroundednessEvaluator,
    "relevance": RelevanceEvaluator,
}


def prompt_version(path: Path) -> str:
    """Which revision of the prompt file this is, `-dirty` included.

    Deliberately identical to call_model.py's function of the same name, so
    that the version this script computes and the version the span recorded are
    comparable at all. If they diverge, the drift check below stops being a
    check and starts being noise.
    """
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(path)],
        capture_output=True, text=True, cwd=path.parent,
    ).stdout.strip()
    if not commit:
        return "uncommitted"
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", str(path)],
        capture_output=True, text=True, cwd=path.parent,
    ).stdout.strip()
    return f"{commit}-dirty" if dirty else commit


def find_prompt(filename: str) -> Path | None:
    for directory in PROMPT_SEARCH_DIRS:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def fetch_call(workspace_id: str, trace_id: str, since: timedelta) -> dict:
    """Read the genaiops.call record this evaluation is about to score.

    Queries the same AppDependencies table query_trace.py reads, narrowed to
    one OperationId.
    """
    query = f"""
    AppDependencies
    | where Name == '{CALL_SPAN_NAME}'
    | where OperationId == '{trace_id}'
    | project
        TimeGenerated,
        TraceId = OperationId,
        PromptFile = tostring(Properties['prompt.file']),
        PromptVersion = tostring(Properties['prompt.version']),
        Deployment = tostring(Properties['gen_ai.request.model']),
        Response = tostring(Properties['gen_ai.response.content'])
    | order by TimeGenerated desc
    | take 1
    """
    client = LogsQueryClient(DefaultAzureCredential())
    result = client.query_workspace(workspace_id, query, timespan=since)

    if result.status == LogsQueryStatus.FAILURE:
        raise RuntimeError(f"Log Analytics query failed: {result.partial_error}")

    rows = list(result.tables[0].rows) if result.tables else []
    if not rows:
        # REFUSED, NOT DEGRADED (contracts/evaluate-and-retrieve.md). An empty
        # response substituted here would still produce a score, and that score
        # would be a real number attached to nothing.
        raise LookupError(
            f"No '{CALL_SPAN_NAME}' span with trace id {trace_id} in the last "
            f"{since}. Ingestion lags a call by 1-3 minutes — widen --since or "
            f"wait before concluding the call was never traced."
        )
    return dict(zip(result.tables[0].columns, rows[0]))


def resolve_from_trace(record: dict, metric: str) -> tuple[str, str | None, str]:
    """Recover the question that was asked, from the prompt file the span names.

    The genaiops.call span records WHICH PROMPT FILE at WHICH REVISION produced
    a response — not the rendered question. So the question is reconstructed by
    loading that same file with the same loader block 3 used to send it.

    That reconstruction is only trustworthy while the file still matches the
    revision the span recorded, which is why the mismatch below is fatal rather
    than a warning: scoring yesterday's answer against today's question
    produces a number that looks exactly like a real result.
    """
    prompt_path = find_prompt(record["PromptFile"])
    if prompt_path is None:
        raise LookupError(
            f"The trace names prompt file {record['PromptFile']!r}, which is not "
            f"in any of: {[str(d) for d in PROMPT_SEARCH_DIRS]}"
        )

    current = prompt_version(prompt_path)
    if current != record["PromptVersion"]:
        raise RuntimeError(
            f"{prompt_path.name} is now at {current}, but the trace was produced "
            f"by {record['PromptVersion']}. Refusing to score: the question "
            f"reconstructed from the working tree is not the question that was "
            f"asked. Check out the recorded revision, or score a fresh call."
        )

    loaded = prompty.load(str(prompt_path))
    messages = prompty.prepare(loaded)
    user_turns = [m["content"] for m in messages if m.get("role") == "user"]
    if not user_turns:
        raise RuntimeError(f"{prompt_path.name} renders no user turn to score.")
    query = user_turns[-1]

    # Groundedness needs a source to check the answer against; relevance does
    # not (verified against the installed SDK's own call signatures). A prompt
    # with no `context` in its sample block cannot be scored for groundedness
    # at all, and saying so beats inventing one.
    context = (loaded.sample or {}).get("context")
    if metric == "groundedness" and not context:
        raise RuntimeError(
            f"{prompt_path.name} has no `context` in its sample block, so there "
            f"is nothing to check groundedness AGAINST. Use --metric relevance, "
            f"or score a prompt that carries its own source material."
        )
    return query, context, record["Response"]


def resolve_from_fixture(path: Path, metric: str) -> tuple[str, str | None, str]:
    data = json.loads(path.read_text())
    missing = [k for k in ("query", "response") if k not in data]
    if metric == "groundedness" and "context" not in data:
        missing.append("context")
    if missing:
        raise RuntimeError(f"{path.name} is missing required key(s): {missing}")
    return data["query"], data.get("context"), data["response"]


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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--trace-id", help="Score a real call, by its trace id.")
    source.add_argument("--fixture", type=Path,
                        help="Score a hand-authored query/context/response JSON file.")
    parser.add_argument("--metric", required=True, choices=sorted(EVALUATORS),
                        help="Which evaluator to run.")
    parser.add_argument("--since", type=parse_since, default=timedelta(hours=2),
                        help="How far back to look for the call (default 2h).")
    args = parser.parse_args()

    endpoint = os.environ.get(ENDPOINT_VAR)
    connection_string = os.environ.get(CONNECTION_STRING_VAR)
    workspace_id = os.environ.get(WORKSPACE_VAR)

    if not endpoint:
        print(f"{ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2
    if not connection_string:
        # Same refusal call_model.py makes, for the same reason: an evaluation
        # that runs but is never exported costs a real model call and proves
        # nothing, and the gap would only surface later as an empty query.
        print(f"{CONNECTION_STRING_VAR} is not set; refusing to run an "
              f"unrecorded evaluation.", file=sys.stderr)
        return 2
    if args.trace_id and not workspace_id:
        print(f"{WORKSPACE_VAR} is not set; cannot read the call to be scored.",
              file=sys.stderr)
        return 2

    # --- Resolve what is being scored, BEFORE spending a judge call ---------
    try:
        if args.trace_id:
            record = fetch_call(workspace_id, args.trace_id, args.since)
            query, context, response = resolve_from_trace(record, args.metric)
            evaluated_trace_id = record["TraceId"]
            evaluated_prompt_version = record["PromptVersion"]
            evaluated_model = record["Deployment"]
        else:
            if not args.fixture.is_file():
                print(f"No fixture at {args.fixture}", file=sys.stderr)
                return 2
            query, context, response = resolve_from_fixture(args.fixture, args.metric)
            # The literal string the data model reserves for a record with no
            # live call behind it, so query_evaluations.py can label the case
            # rather than report a failed join as missing data.
            evaluated_trace_id = "fixture"
            evaluated_prompt_version = prompt_version(args.fixture)
            evaluated_model = "n/a (fixture)"
    except (LookupError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    configure_azure_monitor(
        connection_string=connection_string,
        resource_attributes={"service.name": "ai300-foundry-block4"},
    )
    tracer = trace.get_tracer(__name__)

    credential = DefaultAzureCredential()
    model_config = AzureOpenAIModelConfiguration(
        azure_endpoint=endpoint,
        azure_deployment=JUDGE_DEPLOYMENT,
        api_version=API_VERSION,
        # NO api_key, and none exists to pass: infra/foundry.bicep sets
        # disableLocalAuth. The credential below is handed to the evaluator
        # explicitly rather than left to an implicit fallback, so an auth
        # failure names the credential this script chose.
        credential=credential,
    )
    evaluator = EVALUATORS[args.metric](model_config, credential=credential)

    with tracer.start_as_current_span(SPAN_NAME) as span:
        # SET BEFORE THE JUDGE CALL. Same contract as call_model.py: if the
        # evaluator refuses or the process dies mid-flight, the span still says
        # what was attempted and against what.
        span.set_attribute("eval.metric", args.metric)
        span.set_attribute("eval.evaluated_trace_id", evaluated_trace_id)
        span.set_attribute("prompt.version", evaluated_prompt_version)
        span.set_attribute("gen_ai.request.model", evaluated_model)
        span.set_attribute("eval.judge_model", JUDGE_DEPLOYMENT)

        # No try/except, and that is the contract. A quota refusal or an
        # unparseable judge output is the finding this feature is here to
        # surface — research.md § R5 names exactly this as the check on whether
        # gpt-4.1-mini is a usable judge at all.
        kwargs = {"query": query, "response": response}
        if args.metric == "groundedness":
            kwargs["context"] = context
        result = evaluator(**kwargs)

        score = result.get(args.metric)
        verdict = result.get(f"{args.metric}_result")
        threshold = result.get(f"{args.metric}_threshold")
        reason = result.get(f"{args.metric}_reason")
        status = result.get(f"{args.metric}_status")

        # READ FROM THE EVALUATOR, NOT RECOMPUTED from score and threshold.
        # If the SDK's own pass/fail judgement and a hand-rolled comparison
        # ever disagreed, the hand-rolled one would be the bug.
        if score is not None:
            span.set_attribute("eval.score", float(score))
        if threshold is not None:
            span.set_attribute("eval.threshold", float(threshold))
        span.set_attribute("eval.result", str(verdict))
        span.set_attribute("eval.reason", str(reason))

        trace_id = format(span.get_span_context().trace_id, "032x")

    # Same lesson block 3 paid for once: a span queued in a batch processor is
    # not a span that was exported, and a short-lived CLI process is exactly
    # where that gap opens.
    if not trace.get_tracer_provider().force_flush():
        print("WARNING: the evaluation span was not flushed to Application "
              "Insights; query_evaluations.py will not find it.", file=sys.stderr)

    print(f"--- evaluated: {evaluated_trace_id} ({args.metric}) ---")
    print(f"score      : {score} (threshold {threshold})")
    print(f"result     : {verdict}")
    print(f"reason     : {reason}")
    print(f"--- eval trace_id: {trace_id} ---")

    if status == "skipped" or verdict == "not_applicable":
        # The SDK's third outcome, and neither a pass nor a fail. Surfaced as a
        # non-zero exit so it can never be mistaken for a score — the whole of
        # FR-008's concern, one level up from a missing record.
        print("The evaluator did not produce a score (status "
              f"{status!r}). This is not a failing score — it is no score.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
