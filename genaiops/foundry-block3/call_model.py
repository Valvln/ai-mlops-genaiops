"""Send one completion request to the feature 006 Foundry deployment, traced.

The prompt comes from a tracked .prompty file, and so do the deployment name
and the sampling parameters — the file is the source of truth, not just the
text (FR-006).

Every call emits an OpenTelemetry span carrying the prompt's git revision, the
deployment name, and the response, exported to the Application Insights
resource infra/foundry.bicep creates. Nothing printed below is the record:
query_trace.py reads the record back from Azure in a separate invocation, and
that separation is what makes SC-004 a test rather than a restatement of "the
call happened".

Usage:
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    export APPLICATIONINSIGHTS_CONNECTION_STRING="$(az monitor app-insights component show \
        -g rg-ai300-foundry -a <appi-name> --query connectionString -o tsv)"
    uv run call_model.py [prompts/hello-domain3.prompty]
"""

import os
import subprocess
import sys
from pathlib import Path

import prompty
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.monitor.opentelemetry import configure_azure_monitor
from openai import AzureOpenAI
from opentelemetry import trace

# Not a default. The account name carries uniqueString(resourceGroup().id), so
# a hard-coded endpoint would silently point at a resource group that no longer
# exists the first time this disposable environment is rebuilt.
ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"

# Read from the App Insights resource rather than discovered through the
# Foundry project's own connection. The SDK path for that
# (AIProjectClient.telemetry) needs the data action
# Microsoft.CognitiveServices/accounts/AIServices/connections/read, which
# neither Owner nor Cognitive Services OpenAI User carries — see the long note
# in infra/foundry.bicep for why closing that gap costs more than it buys.
CONNECTION_STRING_VAR = "APPLICATIONINSIGHTS_CONNECTION_STRING"

# Pinned, like the model version in infra/foundry.bicep. An unpinned data-plane
# API version is a dependency that changes without a commit.
API_VERSION = "2024-10-21"

DEFAULT_PROMPT = "prompts/hello-domain3.prompty"

# The span name query_trace.py looks for. Kept as a shared constant rather than
# a literal in each file so the two cannot drift apart silently — a retrieval
# that returns nothing because the writer renamed its span is the failure mode
# this feature exists to rule out.
SPAN_NAME = "genaiops.call"


def prompt_version(path: Path) -> str:
    """Identify which revision of the prompt file this call actually used.

    THE `-dirty` SUFFIX IS THE WHOLE POINT OF THIS FUNCTION. `git log -1` alone
    reports the last commit that touched the file, which is a lie whenever the
    working tree has uncommitted edits — the call would be attributed to a
    revision whose content is not what was sent. Feature 006 exists to make a
    trace answer "which prompt produced this", so an answer that is confidently
    wrong is worse here than no answer at all.
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


def main() -> int:
    endpoint = os.environ.get(ENDPOINT_VAR)
    if not endpoint:
        print(f"{ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2

    connection_string = os.environ.get(CONNECTION_STRING_VAR)
    if not connection_string:
        # Refused rather than degraded. A run that quietly skips tracing would
        # still print a plausible answer, and the gap would only surface later
        # as an empty query — attributed to the wrong cause.
        print(f"{CONNECTION_STRING_VAR} is not set; refusing to make an "
              f"untraced call.", file=sys.stderr)
        return 2

    prompt_path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT).resolve()
    if not prompt_path.is_file():
        print(f"No prompt file at {prompt_path}", file=sys.stderr)
        return 2

    prompt = prompty.load(str(prompt_path))
    # No inputs passed: prompty falls back to the file's own `sample` block, so
    # a run with no arguments is still reproducible from the file alone.
    messages = prompty.prepare(prompt)

    # Read from the frontmatter rather than from a constant in this file. If
    # they disagreed, the prompt file would no longer describe the call it
    # produces, which is the property FR-006 is actually about.
    deployment = prompt.model.configuration["azure_deployment"]
    parameters = dict(prompt.model.parameters)

    version = prompt_version(prompt_path)

    configure_azure_monitor(
        connection_string=connection_string,
        # Names this process in the trace, so a record can be attributed to the
        # harness rather than to an anonymous Python.
        resource_attributes={"service.name": "ai300-foundry-block3"},
    )
    tracer = trace.get_tracer(__name__)

    # No API key, and none available: infra/foundry.bicep sets
    # disableLocalAuth, so the data plane accepts Entra tokens only. This
    # resolves the az-CLI login the author already has.
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=API_VERSION,
    )

    with tracer.start_as_current_span(SPAN_NAME) as span:
        # SET BEFORE THE CALL, NOT AFTER, and that ordering is the contract
        # (contracts/call-and-trace.md § call_model.py, step 2). Attributes
        # written after the request would describe the working tree as it is
        # when the response lands; if the call fails or the process dies
        # mid-flight, the span still has to say which prompt was attempted.
        span.set_attribute("prompt.file", prompt_path.name)
        span.set_attribute("prompt.version", version)
        span.set_attribute("gen_ai.request.model", deployment)

        # NO try/except AROUND THIS CALL, AND THAT IS THE CONTRACT: an
        # authentication or quota refusal is exactly the error this project
        # reads rather than works around. Catching it here would turn a 401
        # into a tidy message and lose the one thing worth having — what the
        # service actually said.
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            **parameters,
        )

        content = response.choices[0].message.content
        # Recorded on the span because SC-004 requires the RESPONSE CONTENT to
        # come back from the query, not just a request id. Safe here only
        # because this feature's prompts are exam questions; a prompt carrying
        # anything personal would make this line a data-protection decision
        # rather than a convenience.
        span.set_attribute("gen_ai.response.content", content)
        span.set_attribute("gen_ai.response.model", response.model)
        span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)

        trace_id = format(span.get_span_context().trace_id, "032x")

    print(f"--- prompt: {prompt_path.name} @ {version} ---")
    print("--- response ---")
    print(content)
    print("--- usage ---")
    print(f"prompt_tokens={response.usage.prompt_tokens} "
          f"completion_tokens={response.usage.completion_tokens} "
          f"total_tokens={response.usage.total_tokens}")
    print(f"model={response.model} id={response.id}")
    # For a human confirming that query_trace.py found the RIGHT record. The
    # query does not need it — it searches by time window — precisely so that
    # retrieval does not depend on anything this process handed over.
    print(f"--- trace_id: {trace_id} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
