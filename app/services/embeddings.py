"""
app/services/embeddings.py
"""

import logging
import os
from typing import List

from sentence_transformers import SentenceTransformer
from supabase import create_client, Client

logger = logging.getLogger(__name__)

MODEL_NAME    = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("[embeddings] Loading %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_supabase() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    vecs = _get_model().encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return vecs.tolist()


def embed_single(text: str) -> List[float]:
    return embed_texts([text])[0]


def embed_and_upsert(chunks: List[str], source: str) -> None:
    if not chunks:
        return
    logger.info("[embeddings] Embedding %d chunks  source=%r", len(chunks), source)
    vectors = embed_texts(chunks)
    rows = [
        {"content": chunk, "source": source, "embedding": vec}
        for chunk, vec in zip(chunks, vectors)
    ]
    supabase = _get_supabase()
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        supabase.table("documents").insert(batch).execute()
    logger.info("[embeddings] Upsert complete  total=%d", len(chunks))