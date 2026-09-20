"""Read the free tier's real limits off the service itself.

THIS IS USER STORY 2 IN ONE FILE, and it exists because of a gap in the
published quota table: it has columns for Basic through L2 and NO COLUMN FOR
FREE. The service storage limit (50 MB) is documented; the vector index quota at
this tier is not documented anywhere, and the only place it can be read is the
service's own /servicestats response.

Raw JSON is printed and nothing is interpreted here. A number that has been
reshaped on its way to the reader is a number whose provenance has to be taken
on trust, and the whole point of this call is that it is the primary source.

WHICH ROLE THIS NEEDS IS THE NON-OBVIOUS PART. /servicestats is guarded by
"access quotas and service statistics", which the permission matrix grants to
Owner, Contributor and Search Service Contributor - and NOT to Search Index Data
Contributor, the role whose name sounds like the data-plane one. A 403 from this
script is that role split, not a free-tier restriction, and reading it as a tier
limitation would produce a confident and completely wrong finding.

Usage:
    export AZURE_SEARCH_ENDPOINT="https://<service>.search.windows.net"
    uv run service_stats.py               # service-level quotas and counters
    uv run service_stats.py --index       # plus the populated index's own stats
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from azure.identity import DefaultAzureCredential

ENDPOINT_VAR = "AZURE_SEARCH_ENDPOINT"
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "exam-notes")

# Pinned, for the reason block 3 pins its data-plane API version: an unpinned
# API version is a dependency that changes without a commit.
API_VERSION = "2025-09-01"

# Not the ARM scope. The search data plane issues tokens for its own audience,
# and presenting a management-plane token here fails as an authentication error
# rather than as a wrong-audience one - which sends the reader looking at roles.
SCOPE = "https://search.azure.com/.default"


def get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # PRINTED VERBATIM AND RE-RAISED. A refusal is the only direct
        # measurement of a boundary this feature has, and US2 scenario 4 says
        # to capture it rather than translate it into a friendlier message.
        body = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code} {exc.reason}\n{body}", file=sys.stderr)
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true",
                    help="also read the index's own document and vector sizes")
    args = ap.parse_args()

    endpoint = os.environ.get(ENDPOINT_VAR, "").rstrip("/")
    if not endpoint:
        print(f"{ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2

    token = DefaultAzureCredential().get_token(SCOPE).token

    print(f"=== GET {endpoint}/servicestats?api-version={API_VERSION}")
    stats = get(f"{endpoint}/servicestats?api-version={API_VERSION}", token)
    print(json.dumps(stats, indent=2))

    if args.index:
        url = f"{endpoint}/indexes/{INDEX_NAME}/stats?api-version={API_VERSION}"
        print(f"\n=== GET {url}")
        print(json.dumps(get(url, token), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
