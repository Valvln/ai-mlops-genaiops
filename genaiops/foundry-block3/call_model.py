"""Send one completion request to the feature 006 Foundry deployment.

The prompt comes from a tracked .prompty file, and so do the deployment name
and the sampling parameters — the file is the source of truth, not just the
text (FR-006). What used to be an inline literal here is now a thing git can
show a diff of; see the previous revision of this file for the before.

Usage:
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    uv run call_model.py [prompts/hello-domain3.prompty]
"""

import os
import subprocess
import sys
from pathlib import Path

import prompty
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

# Not a default. The account name carries uniqueString(resourceGroup().id), so
# a hard-coded endpoint would silently point at a resource group that no longer
# exists the first time this disposable environment is rebuilt.
ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"

# Pinned, like the model version in infra/foundry.bicep. An unpinned data-plane
# API version is a dependency that changes without a commit.
API_VERSION = "2024-10-21"

DEFAULT_PROMPT = "prompts/hello-domain3.prompty"


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

    # NO try/except AROUND THIS CALL, AND THAT IS THE CONTRACT
    # (contracts/call-and-trace.md): an authentication or quota refusal is
    # exactly the error this project reads rather than works around. Catching
    # it here would turn a 401 into a tidy message and lose the one thing worth
    # having — what the service actually said.
    response = client.chat.completions.create(
        model=deployment,
        messages=messages,
        **parameters,
    )

    print(f"--- prompt: {prompt_path.name} @ {version} ---")
    print("--- response ---")
    print(response.choices[0].message.content)
    print("--- usage ---")
    # Printed because it is the evidence for SC-002's second half: the cost of
    # this call is attributable to tokens consumed, not to a standing charge.
    print(f"prompt_tokens={response.usage.prompt_tokens} "
          f"completion_tokens={response.usage.completion_tokens} "
          f"total_tokens={response.usage.total_tokens}")
    print(f"model={response.model} id={response.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
