"""Create the one index all four retrieval methods query.

AN INDEX IS NOT AN ARM RESOURCE, which is why this is a script and not a
resource in infra/search.bicep. The service is control-plane; its schema, its
vector profile and its semantic configuration are data-plane objects, reachable
only with a token for the search audience.

ONE INDEX, FOUR QUERY SHAPES. Nothing here differs between keyword, vector,
hybrid and hybrid-with-semantic-ranking - only the query does. That is what
makes the comparison a comparison rather than four experiments, and it is what
keeps the embedding bill paid exactly once.

Compression and quantization are deliberately absent. Both are levers worth
knowing about, and measuring them is out of scope; adding an unmeasured one
would change the vector index size User Story 2 reports and make that number
about this script's configuration rather than about the tier.

Usage:
    export AZURE_SEARCH_ENDPOINT="https://<service>.search.windows.net"
    uv run create_index.py
"""

import os
import sys

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)

ENDPOINT_VAR = "AZURE_SEARCH_ENDPOINT"
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "exam-notes")

# text-embedding-3-large's native width. Stated as a constant rather than
# inferred from the first vector pushed: a mismatch between what the index
# declares and what the model emits is rejected at push time with an error about
# dimensions, and having the number in one place makes that error legible.
VECTOR_DIMENSIONS = 3072

VECTOR_PROFILE = "hnsw-cosine"
ALGORITHM = "hnsw-default"
SEMANTIC_CONFIG = "default"


def build_index() -> SearchIndex:
    fields = [
        # The document key. URL-safe by construction in chunk_corpus.py - the
        # key travels in request paths, so the heading text could not serve.
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        # Filterable so a later reader can ask "which note did this come from",
        # facetable so the distribution across notes is one query rather than a
        # scan. Neither is used by the four methods; both are cheap and make the
        # index answerable about itself.
        SimpleField(name="note", type=SearchFieldDataType.String,
                    filterable=True, facetable=True),
        # SEARCHABLE, NOT SIMPLE, and that is the load-bearing choice: the
        # semantic configuration below names this as its title field, and a
        # non-searchable field cannot be one.
        SearchableField(name="heading", type=SearchFieldDataType.String),
        # The chunk text itself. Default analyzer (standard.lucene) - BM25 over
        # it is the `keyword` method, and half of `hybrid`.
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="token_count", type=SearchFieldDataType.Int32,
                    filterable=True),
        # Which revision of docs/exam-notes this document was cut from. The
        # index and the working tree drift apart the moment a note is edited,
        # and this field is what lets a result say so instead of quietly
        # describing a corpus that no longer exists.
        SimpleField(name="corpus_commit", type=SearchFieldDataType.String,
                    filterable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            # Never returned to the caller. 3072 floats per hit, times ten hits,
            # times four methods, times twenty questions is a great deal of
            # traffic carrying no information the comparison uses.
            hidden=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name=ALGORITHM,
                # DEFAULT PARAMETERS ON PURPOSE (m=4, efConstruction=400,
                # efSearch=500). Tuning them is a real lever and an unmeasured
                # one here; leaving them at the service default means the
                # `vector` column of the comparison describes what a reader gets
                # out of the box, which is the thing worth knowing.
                #
                # COSINE, and not because it is the default - it is what
                # text-embedding-3-large's vectors are normalised for. A metric
                # that disagrees with the embedding model produces a ranking
                # that is wrong without being erroneous: every call succeeds.
                parameters=HnswParameters(
                    metric=VectorSearchAlgorithmMetric.COSINE
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE,
                algorithm_configuration_name=ALGORITHM,
            )
        ],
    )

    # The fourth method's entire apparatus. Without semanticSearch: 'free' on
    # the service (infra/search.bicep) this configuration deploys and then
    # refuses at query time, so the template and this file have to agree.
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="heading"),
                    content_fields=[SemanticField(field_name="content")],
                ),
            )
        ]
    )

    return SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def main() -> int:
    endpoint = os.environ.get(ENDPOINT_VAR, "").rstrip("/")
    if not endpoint:
        print(f"{ENDPOINT_VAR} is not set.", file=sys.stderr)
        return 2

    # No key, and none available: infra/search.bicep sets disableLocalAuth, so
    # the data plane accepts Entra tokens only. This resolves the az-CLI login.
    client = SearchIndexClient(endpoint=endpoint,
                               credential=DefaultAzureCredential())

    # create_or_update rather than create. The templates in this repository are
    # deployed twice to prove they are re-runnable, and a script that is
    # one-shot would be the weak link in that claim. It is also NOT destructive:
    # a schema change that would invalidate existing documents is refused by the
    # service rather than applied, which is the right failure.
    result = client.create_or_update_index(build_index())

    print(f"index: {result.name}")
    print(f"fields: {', '.join(f.name for f in result.fields)}")
    print(f"vector profiles: "
          f"{', '.join(p.name for p in result.vector_search.profiles)} "
          f"({VECTOR_DIMENSIONS} dimensions, "
          f"{result.vector_search.algorithms[0].parameters.metric})")
    print(f"semantic configurations: "
          f"{', '.join(c.name for c in result.semantic_search.configurations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
