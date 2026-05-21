"""
app/services/vector_store/qdrant_service.py

Qdrant wrapper — collection management, upsert, similarity search.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.core.logging import logger

# ─── Singleton client ────────────────────────────────────────────────────────
_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=True,         # faster for bulk upserts
            timeout=300,              # Increased to 300s for large files
        )
        logger.info("qdrant.client.created", host=settings.qdrant_host)
    return _client


VECTOR_SIZE = 384   # all-MiniLM-L6-v2 output dimension


def ensure_collection(collection_name: str = settings.qdrant_collection_name) -> None:
    """Create collection if it doesn't exist. Safe to call on every startup."""
    client = get_qdrant_client()
    try:
        client.get_collection(collection_name)
        logger.info("qdrant.collection.exists", name=collection_name)
    except (UnexpectedResponse, Exception):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_SIZE,
                distance=qmodels.Distance.COSINE,
            ),
            hnsw_config=qmodels.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10_000,
            ),
            optimizers_config=qmodels.OptimizersConfigDiff(
                indexing_threshold=20_000,
            ),
        )
        logger.info("qdrant.collection.created", name=collection_name)
        
        # Create payload indices to support fast filtering by document name or timestamp
        client.create_payload_index(
            collection_name=collection_name,
            field_name="filename",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        client.create_payload_index(
            collection_name=collection_name,
            field_name="timestamp",
            field_schema=qmodels.PayloadSchemaType.DATETIME,
        )
        logger.info("qdrant.indices.created", name=collection_name)


def upsert_chunks(
    chunks_with_embeddings: List[dict],
    collection_name: str = settings.qdrant_collection_name,
) -> List[str]:
    """
    Upsert a batch of chunks into Qdrant.

    Each item in chunks_with_embeddings must have:
        {
            "text": str,
            "embedding": List[float],
            "document_id": str,
            "filename": str,
            "chunk_index": int,
            "page_number": int | None,
            "section": str | None,
            "timestamp": str,
            "meta": dict,
        }

    Returns list of Qdrant point IDs (UUIDs as strings).
    """
    client = get_qdrant_client()
    points, ids = [], []

    for item in chunks_with_embeddings:
        point_id = str(uuid.uuid4())
        ids.append(point_id)
        points.append(
            qmodels.PointStruct(
                id=point_id,
                vector=item["embedding"],
                payload={
                    "text":         item["text"],
                    "document_id":  item["document_id"],
                    "filename":     item["filename"],
                    "chunk_index":  item["chunk_index"],
                    "page_number":  item.get("page_number"),
                    "section":      item.get("section"),
                    "timestamp":    item["timestamp"],
                    "element_type": item.get("element_type", "text"),
                    **item.get("meta", {}),
                },
            )
        )

    # Batch upserts into smaller chunks to prevent engine TIMEOUT
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        # wait=False allows Qdrant to acknowledge the payload immediately
        # and process the indexing asynchronously, preventing HTTP timeouts.
        client.upsert(collection_name=collection_name, points=batch, wait=False)
    
    logger.info("qdrant.upsert.done", count=len(points))
    return ids


def similarity_search(
    query_embedding: List[float],
    top_k: int = 5,
    document_id: Optional[str] = None,
    collection_name: str = settings.qdrant_collection_name,
) -> List[dict]:
    """
    Cosine similarity search. Optionally filter by document_id.
    Returns list of {"text", "score", "document_id", "page_number", ...}
    """
    client = get_qdrant_client()

    query_filter = None
    if document_id:
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchValue(value=document_id),
                )
            ]
        )

    results = client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "text":        hit.payload.get("text", ""),
            "score":       hit.score,
            "document_id": hit.payload.get("document_id"),
            "page_number": hit.payload.get("page_number"),
            "chunk_index": hit.payload.get("chunk_index"),
            "qdrant_id":   hit.id,
        }
        for hit in results
    ]


def delete_document_vectors(
    document_id: str,
    collection_name: str = settings.qdrant_collection_name,
) -> None:
    """Delete all vectors belonging to a document."""
    client = get_qdrant_client()
    client.delete(
        collection_name=collection_name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    )
                ]
            )
        ),
    )
    logger.info("qdrant.delete.done", document_id=document_id)
