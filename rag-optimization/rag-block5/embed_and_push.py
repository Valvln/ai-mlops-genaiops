"""Embed the chunks locally and push them to the index over the data plane.

WHY PUSH, AND NOT AN INDEXER WITH INTEGRATED VECTORIZATION - which is the path
every Learn tutorial takes. Two independent free-tier reasons, and the first one
is the one that decided it:

  1. The free tier grants NO MANAGED IDENTITY for an indexer's outbound
     connections. An indexer would therefore need a key-bearing connection
     string to reach its data source and its embedding skill - reintroducing
     exactly the credential that disableLocalAuth removed from both services.
  2. Indexers on the free tier are capped at 1-3 minutes of runtime (3-10 with a
     skillset) and 20 enrichment transactions per indexer per day.

Reason 1 is a posture decision and reason 2 is an inconvenience. Documented
together in the write-up as a case study, because the mechanism NOT used is the
examinable half: knowing why integrated vectorization is unavailable here is
worth more than having used it without noticing what it costs.

THE ONE STEP IN THIS FEATURE THAT SPENDS MONEY, and it is a fraction of a cent.
~73.000 tokens at EUR 0.0002 per 1K is about EUR 0.015, paid once - the four
retrieval methods share this corpus and re-embedding is never needed to change
the method.

Usage:
    export AZURE_SEARCH_ENDPOINT="https://<service>.search.windows.net"
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    uv run embed_and_push.py [--dry-run]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from openai import AzureOpenAI

CHUNKS_PATH = Path(__file__).resolve().parent / "chunks.jsonl"

SEARCH_ENDPOINT_VAR = "AZURE_SEARCH_ENDPOINT"
FOUNDRY_ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "exam-notes")

EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
# Pinned, like block 3's. An unpinned data-plane API version is a dependency
# that changes without a commit.
API_VERSION = "2024-10-21"

# THE DEPLOYMENT'S CAPACITY IS 10, WHICH IS 10.000 TOKENS PER MINUTE. Block 4's
# F3 is the reason this script paces itself instead of firing everything at
# once: capacity buys requests per minute as well as tokens, and a burst of
# back-to-back embedding calls 429s on contact. 20 chunks is roughly 7.000
# tokens - one batch comfortably inside one minute's allowance.
BATCH_CHUNKS = 20
TOKENS_PER_MINUTE = 10_000

# The service accepts up to 1000 documents or 16 MB per indexing request. 3072
# floats of JSON is ~35 KB per document, so the size limit binds long before the
# count does: 100 documents is ~3.5 MB, well inside it.
PUSH_BATCH = 100


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="count what would be embedded and spend nothing")
    args = ap.parse_args()

    if not CHUNKS_PATH.is_file():
        print(f"No {CHUNKS_PATH.name}; run chunk_corpus.py first.",
              file=sys.stderr)
        return 2

    chunks = [json.loads(line) for line in
              CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line]
    planned = sum(c["token_count"] for c in chunks)

    commits = {c["corpus_commit"] for c in chunks}
    print(f"{len(chunks)} chunks, {planned} tokens, "
          f"corpus_commit {', '.join(sorted(commits))}")
    print(f"estimated cost: EUR {planned / 1000 * 0.0002:.4f}")
    if any(c.endswith("-dirty") for c in commits):
        # NOT A FATAL ERROR, BUT NOT SILENT EITHER. An index built from an
        # uncommitted tree cannot be rebuilt from the repository, and the label
        # set that follows is anchored to chunk ids this corpus produced. The
        # author decides; the script refuses to let it pass unnoticed.
        print("WARNING: the corpus has uncommitted changes. The chunk ids "
              "below are not reproducible from any commit.", file=sys.stderr)

    if args.dry_run:
        print("--dry-run: nothing embedded, nothing pushed.")
        return 0

    search_endpoint = os.environ.get(SEARCH_ENDPOINT_VAR, "").rstrip("/")
    foundry_endpoint = os.environ.get(FOUNDRY_ENDPOINT_VAR)
    if not search_endpoint or not foundry_endpoint:
        print(f"{SEARCH_ENDPOINT_VAR} and {FOUNDRY_ENDPOINT_VAR} must be set.",
              file=sys.stderr)
        return 2

    # ONE CREDENTIAL, TWO AUDIENCES. The same az-CLI login is exchanged for a
    # cognitiveservices token to embed and a search token to push. No key is
    # involved on either side, and none is available: both services have
    # disableLocalAuth set.
    credential = DefaultAzureCredential()

    openai_client = AzureOpenAI(
        azure_endpoint=foundry_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"),
        api_version=API_VERSION,
        # Above the SDK default of 2. A 429 here is a pacing problem with a
        # known cure, not a fault to surface - unlike the authorization errors
        # block 3 deliberately leaves uncaught.
        max_retries=5,
    )
    search_client = SearchClient(endpoint=search_endpoint,
                                 index_name=INDEX_NAME,
                                 credential=credential)

    documents = []
    embedded_tokens = 0
    started = time.monotonic()

    for start in range(0, len(chunks), BATCH_CHUNKS):
        batch = chunks[start:start + BATCH_CHUNKS]
        response = openai_client.embeddings.create(
            model=EMBEDDING_DEPLOYMENT,
            input=[c["content"] for c in batch],
        )
        # THE SERVICE'S OWN COUNT, NOT tiktoken's. The two should agree, and
        # SC-006 is about what a measurement says rather than what a prediction
        # says - so the billed number is the one recorded.
        embedded_tokens += response.usage.total_tokens

        for chunk, item in zip(batch, response.data):
            documents.append({**chunk, "content_vector": item.embedding})

        done = start + len(batch)
        print(f"  embedded {done}/{len(chunks)} chunks "
              f"({embedded_tokens} tokens billed)")

        # Pace against the deployment's tokens-per-minute allowance rather than
        # sleeping a fixed interval: a fixed sleep is either too slow or too
        # fast the moment the corpus or the capacity changes.
        if done < len(chunks):
            entitled = embedded_tokens / TOKENS_PER_MINUTE * 60
            behind = entitled - (time.monotonic() - started)
            if behind > 0:
                time.sleep(behind)

    print(f"\nembedded {len(documents)} chunks, "
          f"{embedded_tokens} tokens billed "
          f"(EUR {embedded_tokens / 1000 * 0.0002:.4f})")

    uploaded = 0
    for start in range(0, len(documents), PUSH_BATCH):
        results = search_client.upload_documents(
            documents[start:start + PUSH_BATCH])
        # CHECKED, NOT ASSUMED. upload_documents returns per-document results
        # and does NOT raise when individual documents are rejected: a partial
        # failure looks exactly like a success from the call site, and the index
        # would then be quietly short of documents that the comparison silently
        # never retrieves.
        failed = [r for r in results if not r.succeeded]
        if failed:
            for r in failed:
                print(f"FAILED {r.key}: {r.error_message}", file=sys.stderr)
            return 1
        uploaded += len(results)
        print(f"  pushed {uploaded}/{len(documents)}")

    print(f"\npushed {uploaded} documents to '{INDEX_NAME}'.")
    print("Index statistics lag ingestion by a few seconds; "
          "run service_stats.py --index to read them back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
