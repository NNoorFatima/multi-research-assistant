"""
app/services/retriever.py

Supabase pgvector retrieval service.

Queries the `documents` table using a Postgres RPC function
`match_documents` that performs cosine-similarity search.

Required SQL function (run once in Supabase SQL editor):
────────────────────────────────────────────────────────────────
create or replace function match_documents (
    query_embedding  vector(384),
    match_count      int      default 5,
    filter           jsonb    default '{}'
)
returns table (
    id          uuid,
    content     text,
    source      text,
    similarity  float
)
language plpgsql
as $$
begin
    return query
    select
        d.id,
        d.content,
        d.source,
        1 - (d.embedding <=> query_embedding) as similarity
    from documents d
    where
        -- optional metadata filter: e.g. '{"source": "report.pdf"}'
        ( filter = '{}'::jsonb or d.source = filter->>'source' )
    order by d.embedding <=> query_embedding
    limit match_count;
end;
$$;
────────────────────────────────────────────────────────────────

Public API:
  retrieve_chunks(query, top_k, filter_metadata) -> List[RetrievedChunk]
  similarity_search(embedding, top_k, filter)    -> List[RetrievedChunk]
"""

import logging
import os
from typing import List, Optional

from supabase import create_client, Client

from app.graph.state import RetrievedChunk
from app.services.embeddings import embed_single

logger = logging.getLogger(__name__)

# Minimum similarity score — chunks below this are discarded
SIMILARITY_THRESHOLD = 0.30


# ── Supabase client ──────────────────────────────────────────────────────────

def _get_supabase() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_ANON_KEY"],   # anon key is fine for reads
    )


# ── Main retrieval function ──────────────────────────────────────────────────

def retrieve_chunks(
    query: str,
    top_k: int = 5,
    filter_metadata: Optional[dict] = None,
) -> List[RetrievedChunk]:
    """
    Full pipeline: embed query → similarity search → filter by threshold.

    Args:
        query           : Raw user query string.
        top_k           : Number of chunks to return (before threshold filtering).
        filter_metadata : Optional dict passed to the SQL RPC, e.g.
                          {"source": "annual_report.pdf"}
                          Pass None or {} for no filtering.

    Returns:
        List of RetrievedChunk dicts sorted by similarity descending.
        Returns [] on any error (nodes handle gracefully).
    """
    logger.info("[retriever] Retrieving top-%d chunks  query=%r", top_k, query[:80])

    # ── 1. Embed the query ───────────────────────────────────────
    try:
        query_embedding = embed_single(query)
    except Exception as exc:
        logger.error("[retriever] Embedding failed: %s", exc)
        return []

    # ── 2. Similarity search ─────────────────────────────────────
    return similarity_search(
        embedding=query_embedding,
        top_k=top_k,
        filter_metadata=filter_metadata,
    )


def similarity_search(
    embedding: List[float],
    top_k: int = 5,
    filter_metadata: Optional[dict] = None,
) -> List[RetrievedChunk]:
    """
    Direct vector search using a pre-computed embedding.
    Useful when you already have the embedding (avoids double-encoding).

    Args:
        embedding       : 384-dim float vector.
        top_k           : Max results to fetch from Supabase.
        filter_metadata : Optional {"source": "..."} filter.

    Returns:
        Filtered, sorted List[RetrievedChunk].
    """
    supabase = _get_supabase()
    filter_json = filter_metadata or {}

    try:
        response = (
            supabase.rpc(
                "match_documents",
                {
                    "query_embedding": embedding,
                    "match_count":     top_k,
                    "filter":          filter_json,
                },
            )
            .execute()
        )
    except Exception as exc:
        logger.error("[retriever] Supabase RPC failed: %s", exc)
        return []

    if not response.data:
        logger.info("[retriever] No results returned from Supabase")
        return []

    # ── 3. Map rows → RetrievedChunk, apply threshold ────────────
    chunks: List[RetrievedChunk] = []
    for row in response.data:
        sim = float(row.get("similarity", 0.0))
        if sim < SIMILARITY_THRESHOLD:
            logger.debug("[retriever] Skipping chunk (sim=%.3f < threshold)", sim)
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id   = str(row.get("id", "")),
                content    = row.get("content", ""),
                source     = row.get("source", "unknown"),
                similarity = sim,
            )
        )

    # Sort highest similarity first (RPC already orders, but be explicit)
    chunks.sort(key=lambda c: c["similarity"], reverse=True)

    logger.info(
        "[retriever] Returning %d/%d chunks above threshold=%.2f",
        len(chunks), len(response.data), SIMILARITY_THRESHOLD,
    )
    return chunks