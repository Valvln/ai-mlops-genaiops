"""Run one question set through one retrieval method and record what came back.

FOUR METHODS, ONE INDEX, ONE EMBEDDING PER QUESTION. Nothing about the index
differs between the methods - only the query does. That is what makes this a
comparison rather than four experiments, and it is why changing the method costs
nothing while changing the chunking would cost the whole corpus again.

    keyword           search_text only              -> BM25          @search.score
    vector            vector_queries only           -> cosine        @search.score
    hybrid            both                          -> RRF           @search.score
    hybrid_semantic   both + query_type='semantic'  -> L2 reranker   @search.rerankerScore

WHY EVERY ROW CARRIES score_field. Three incompatible ranges arrive under two
property names: BM25 is unbounded, cosine similarity is 0-1, and RRF is a sum of
1/(rank + 60) terms - all three surface as @search.score. Semantic reranking
surfaces as @search.rerankerScore, 0-4. Four columns of these numbers side by
side is a table that invites exactly one wrong conclusion, so the property name
travels with the value and the comparison is made on the scale-free metrics in
score_retrieval.py instead.

Query embeddings are cached on disk and reused across all four methods. Not an
optimisation - a correctness property: the vector, hybrid and hybrid_semantic
runs must be asking with the SAME vector, or the difference between them is
partly noise from a re-embedding.

Usage:
    export AZURE_SEARCH_ENDPOINT="https://<service>.search.windows.net"
    export AZURE_AI_FOUNDRY_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
    uv run run_retrieval.py --method keyword
    uv run run_retrieval.py --method all
"""

import argparse
import json
import os
import sys
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions" / "questions.jsonl"
RUNS_DIR = HERE / "runs"
EMBEDDING_CACHE = RUNS_DIR / "query-embeddings.json"

SEARCH_ENDPOINT_VAR = "AZURE_SEARCH_ENDPOINT"
FOUNDRY_ENDPOINT_VAR = "AZURE_AI_FOUNDRY_ENDPOINT"
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "exam-notes")

EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
API_VERSION = "2024-10-21"
SEMANTIC_CONFIG = "default"
VECTOR_FIELD = "content_vector"

# Ten, and the same ten for every method. The evaluator's metrics are computed
# at 3 (ndcg@3, xdcg@3, top3_max_relevance), so 10 gives the pool something to
# pool while keeping labelling finite.
TOP_K = 10

METHODS = ("keyword", "vector", "hybrid", "hybrid_semantic")

# The two properties the service can rank by. Read from the result rather than
# assumed: an empty rerankerScore on a method believed to be semantic would mean
# the semantic configuration never engaged, and the run would look healthy.
SCORE_FIELD = "@search.score"
# The SDK exposes the reranker score under BOTH "@search.rerankerScore" (the
# wire name) and "@search.reranker_score" (a snake_case alias), verified to
# carry identical values. The snake_case one is used here and the wire name is
# what gets written into the run, since that is the name the documentation and
# the REST responses use.
RERANKER_FIELD = "@search.reranker_score"


def load_questions() -> list[dict]:
    return [json.loads(line) for line in
            QUESTIONS_PATH.read_text(encoding="utf-8").splitlines() if line]


def query_embeddings(questions: list[dict]) -> dict[str, list[float]]:
    """Embed each query once, ever, and cache it on disk.

    The cache is keyed by question_id. A changed query text under an unchanged
    id would silently reuse the old vector, so the query text is stored beside
    the vector and a mismatch re-embeds rather than being trusted.
    """
    RUNS_DIR.mkdir(exist_ok=True)
    cache = {}
    if EMBEDDING_CACHE.is_file():
        cache = json.loads(EMBEDDING_CACHE.read_text(encoding="utf-8"))

    missing = [q for q in questions
               if q["question_id"] not in cache
               or cache[q["question_id"]]["query"] != q["query"]]

    if missing:
        endpoint = os.environ.get(FOUNDRY_ENDPOINT_VAR)
        if not endpoint:
            print(f"{FOUNDRY_ENDPOINT_VAR} is not set and "
                  f"{len(missing)} queries are not cached.", file=sys.stderr)
            raise SystemExit(2)
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default"),
            api_version=API_VERSION,
            max_retries=5,
        )
        response = client.embeddings.create(
            model=EMBEDDING_DEPLOYMENT,
            input=[q["query"] for q in missing],
        )
        for question, item in zip(missing, response.data):
            cache[question["question_id"]] = {
                "query": question["query"],
                "vector": item.embedding,
            }
        EMBEDDING_CACHE.write_text(json.dumps(cache), encoding="utf-8")
        print(f"embedded {len(missing)} queries "
              f"({response.usage.total_tokens} tokens, "
              f"EUR {response.usage.total_tokens / 1000 * 0.0002:.5f})")
    else:
        print(f"all {len(questions)} query embeddings served from cache")

    return {qid: entry["vector"] for qid, entry in cache.items()}


def search_args(method: str, query: str, vector: list[float]) -> dict:
    """The ONLY thing that differs between the four runs."""
    vector_query = VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=TOP_K,
        fields=VECTOR_FIELD,
    )
    # ⚠️ Two different things are called k here and they are unrelated: this
    # k_nearest_neighbors is how many neighbours the vector leg fetches, while
    # RRF's k = 60 is the rank discount constant inside the fusion.
    base = {
        "top": TOP_K,
        "select": ["chunk_id", "note", "heading", "corpus_commit"],
    }
    if method == "keyword":
        return {**base, "search_text": query}
    if method == "vector":
        # search_text=None, not "": an empty string is still a text query and
        # would make this a hybrid run wearing the vector run's name.
        return {**base, "search_text": None, "vector_queries": [vector_query]}
    if method == "hybrid":
        return {**base, "search_text": query, "vector_queries": [vector_query]}
    if method == "hybrid_semantic":
        return {
            **base,
            "search_text": query,
            "vector_queries": [vector_query],
            "query_type": "semantic",
            "semantic_configuration_name": SEMANTIC_CONFIG,
        }
    raise ValueError(method)


def run(client: SearchClient, method: str, questions: list[dict],
        vectors: dict[str, list[float]]) -> Path:
    out_path = RUNS_DIR / f"{method}.jsonl"
    rows = []
    empty = []

    for question in questions:
        qid = question["question_id"]
        results = client.search(
            **search_args(method, question["query"], vectors[qid]))

        retrieved = []
        commits = set()
        for rank, doc in enumerate(results, start=1):
            commits.add(doc["corpus_commit"])
            reranker = doc.get(RERANKER_FIELD)
            # THE RANKING SCORE IS WHICHEVER ONE ORDERED THIS LIST. For the
            # semantic method that is the reranker score; the @search.score is
            # still present and is the first-stage RRF value, which did NOT
            # determine the final order.
            if method == "hybrid_semantic" and reranker is not None:
                score, field = reranker, "@search.rerankerScore"
            else:
                score, field = doc[SCORE_FIELD], "@search.score"
            retrieved.append({
                "chunk_id": doc["chunk_id"],
                "rank": rank,
                "score": score,
                "score_field": field,
                "note": doc["note"],
                "heading": doc["heading"],
            })

        if not retrieved:
            empty.append(qid)
        rows.append({
            "question_id": qid,
            "method": method,
            "kind": question["kind"],
            # Read off the index rather than off the local chunks file: this is
            # the commit the DOCUMENTS say they came from, which is the only
            # version of the claim that survives the working tree moving on. A
            # set, because an index holding two commits at once is a mixed
            # corpus and the run has to say so instead of picking one.
            "corpus_commit": sorted(commits),
            "retrieved": retrieved,
        })

    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    fields = {r["score_field"] for row in rows for r in row["retrieved"]}
    print(f"{method:<16} {len(rows)} questions, "
          f"{sum(len(r['retrieved']) for r in rows)} results, "
          f"ranked by {', '.join(sorted(fields)) or '(nothing returned)'}")
    if empty:
        # Not an error. For a control question it is the CORRECT outcome, and
        # for an answerable one it is a finding.
        print(f"  no results for: {', '.join(empty)}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True,
                    choices=(*METHODS, "all"))
    args = ap.parse_args()

    endpoint = os.environ.get(SEARCH_ENDPOINT_VAR, "").rstrip("/")
    if not endpoint:
        print(f"{SEARCH_ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2

    questions = load_questions()
    vectors = query_embeddings(questions)

    client = SearchClient(endpoint=endpoint, index_name=INDEX_NAME,
                          credential=DefaultAzureCredential())

    for method in (METHODS if args.method == "all" else (args.method,)):
        run(client, method, questions, vectors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
