"""Send one completion request to the feature 006 Foundry deployment.

User Story 1 only, deliberately: an inline prompt, no tracing, no .prompty
file. The point of keeping this form first is that it proves the deployment
answers a call WITHOUT depending on either P2 story existing — which is what
makes User Story 1 independently testable rather than testable-once-the-rest-
is-built.

Usage:
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    uv run call_model.py
"""

import os
import sys

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

# Not a default. The account name carries uniqueString(resourceGroup().id), so
# a hard-coded endpoint would silently point at a resource group that no longer
# exists the first time this disposable environment is rebuilt.
ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"

DEPLOYMENT_NAME = "gpt-4.1-mini"

# Pinned, like the model version in infra/foundry.bicep. An unpinned data-plane
# API version is a dependency that changes without a commit.
API_VERSION = "2024-10-21"

# Inline ON PURPOSE at this stage — see the module docstring. Feature 006's
# User Story 2 replaces this with a tracked .prompty file, and the diff between
# the two is itself the evidence FR-006 asks for.
SYSTEM_PROMPT = "You are a concise assistant. Answer in at most three sentences."
USER_PROMPT = (
    "Explain the difference between a Standard and a Provisioned model "
    "deployment in Azure AI Foundry."
)


def main() -> int:
    endpoint = os.environ.get(ENDPOINT_VAR)
    if not endpoint:
        print(f"{ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2

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
        model=DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        max_tokens=200,
        temperature=0.2, 
    )

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
