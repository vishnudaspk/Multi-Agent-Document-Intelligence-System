"""
app/services/llm/embedding_service.py

sentence-transformers embedding service.
Uses a process-level singleton so the model is loaded once per worker.
"""
from __future__ import annotations

from typing import List, Optional

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import logger

_model: Optional[SentenceTransformer] = None
BATCH_SIZE = 256   # Increased to push GPU harder


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("embedding.model.loading", model=settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model, device="cuda")
        logger.info("embedding.model.ready", model=settings.embedding_model)
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Batch-embed a list of strings.
    Returns a list of float vectors (length = VECTOR_SIZE = 384).
    """
    model = get_embedding_model()
    if not texts:
        return []

    # process in batches to avoid OOM
    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vecs = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        all_embeddings.extend(vecs.tolist())

    logger.debug("embedding.done", count=len(all_embeddings))
    return all_embeddings


def embed_query(text: str) -> List[float]:
    """Embed a single query string."""
    return embed_texts([text])[0]
