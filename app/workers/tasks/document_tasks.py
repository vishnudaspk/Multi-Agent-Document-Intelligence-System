"""
app/workers/tasks/document_tasks.py

Full ingestion pipeline:
  1. Parse document  (unstructured → docling fallback)
  2. Embed chunks    (sentence-transformers)
  3. Upsert vectors  (Qdrant)
  4. Persist chunks  (PostgreSQL)
  5. Update document status
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import logger
from app.db.models.document import Document, DocumentChunk, DocumentStatus, ProcessingJob
from app.services.document_parser.parser import parse_document
from app.services.llm.embedding_service import embed_texts
from app.services.vector_store.qdrant_service import ensure_collection, upsert_chunks
from app.workers.celery_app import celery_app

# ── Sync SQLAlchemy engine for Celery workers ─────────────────────────────────
# Celery workers are NOT async — use the sync psycopg2 driver.
_SYNC_DB_URL = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
).replace("postgresql://", "postgresql+psycopg2://")

_sync_engine = create_engine(_SYNC_DB_URL, pool_pre_ping=True, pool_size=5)
SyncSession = sessionmaker(bind=_sync_engine, expire_on_commit=False)


def _get_sync_db() -> Session:
    return SyncSession()


# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.ingest_document",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def ingest_document(self, document_id: str, file_path: str) -> dict:
    """
    Full document ingestion pipeline (sync Celery task).
    """
    doc_uuid = uuid.UUID(document_id)
    db: Session = _get_sync_db()

    try:
        # ── 1. Mark job as processing ─────────────────────────────────────────
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found in DB")

        job = db.query(ProcessingJob).filter(
            ProcessingJob.document_id == doc_uuid
        ).order_by(ProcessingJob.created_at.desc()).first()

        doc.status = DocumentStatus.PROCESSING
        if job:
            job.status   = DocumentStatus.PROCESSING
            job.celery_id = self.request.id
            job.started_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("ingest.start", document_id=document_id, path=file_path)

        # ── 2. Parse ──────────────────────────────────────────────────────────
        chunks = parse_document(file_path, doc.filename)
        if not chunks:
            raise ValueError("Parser returned zero chunks")

        logger.info("ingest.parsed", document_id=document_id, chunk_count=len(chunks))

        # ── 3. Embed ──────────────────────────────────────────────────────────
        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)
        logger.info("ingest.embedded", document_id=document_id, vec_count=len(embeddings))

        # ── 4. Upsert to Qdrant ───────────────────────────────────────────────
        ensure_collection()
        
        timestamp_str = doc.created_at.isoformat() if doc.created_at else datetime.now(timezone.utc).isoformat()
        
        payload = [
            {
                "text":         c.text,
                "embedding":    embeddings[i],
                "document_id":  document_id,
                "filename":     doc.filename,
                "chunk_index":  c.chunk_index,
                "page_number":  c.page_number,
                "section":      c.section,
                "timestamp":    timestamp_str,
                "element_type": c.element_type,
                "meta":         c.meta,
            }
            for i, c in enumerate(chunks)
        ]
        qdrant_ids = upsert_chunks(payload)
        logger.info("ingest.upserted", document_id=document_id, points=len(qdrant_ids))

        # ── 5. Persist chunks to PostgreSQL ───────────────────────────────────
        db_chunks = [
            DocumentChunk(
                id=uuid.UUID(qdrant_ids[i]),
                document_id=doc_uuid,
                chunk_index=c.chunk_index,
                text=c.text,
                qdrant_id=qdrant_ids[i],
                page_number=c.page_number,
                meta=c.meta,
            )
            for i, c in enumerate(chunks)
        ]
        db.bulk_save_objects(db_chunks)

        # ── 6. Mark completed ─────────────────────────────────────────────────
        doc.status = DocumentStatus.COMPLETED
        if job:
            job.status      = DocumentStatus.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("ingest.done", document_id=document_id)
        return {
            "status":      "completed",
            "document_id": document_id,
            "chunks":      len(chunks),
        }

    except Exception as exc:
        logger.error("ingest.error", document_id=document_id, error=str(exc))
        try:
            doc = db.query(Document).filter(Document.id == doc_uuid).first()
            if doc:
                doc.status    = DocumentStatus.FAILED
                doc.error_msg = str(exc)
            job = db.query(ProcessingJob).filter(
                ProcessingJob.document_id == doc_uuid
            ).order_by(ProcessingJob.created_at.desc()).first()
            if job:
                job.status      = DocumentStatus.FAILED
                job.error_msg   = str(exc)
                job.finished_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as db_exc:
            logger.error("ingest.db_rollback_failed", error=str(db_exc))

        raise self.retry(exc=exc)

    finally:
        db.close()
