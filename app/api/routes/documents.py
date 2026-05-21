"""
app/api/routes/documents.py

Endpoints:
  POST   /documents/upload    — upload a file, queue ingestion job
  GET    /documents           — list all documents
  GET    /documents/{id}      — get document + job status
  DELETE /documents/{id}      — delete document, vectors, and DB rows
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.models.document import Document, DocumentStatus, ProcessingJob
from app.db.session import get_db
from app.services.vector_store.qdrant_service import delete_document_vectors
from app.workers.tasks.document_tasks import ingest_document

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".txt", ".md", ".html",
    ".png", ".jpg", ".jpeg",
}
MAX_FILE_SIZE_MB = 500


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    id: str
    celery_id: Optional[str]
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    error_msg: Optional[str]

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    status: str
    error_msg: Optional[str]
    created_at: str
    latest_job: Optional[JobResponse]

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    document_id: str
    job_id: str
    celery_task_id: str
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_file(upload: UploadFile) -> None:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{ext}' not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )


def _doc_to_response(doc: Document) -> DocumentResponse:
    latest_job = None
    if doc.jobs:
        j = sorted(doc.jobs, key=lambda x: x.created_at, reverse=True)[0]
        latest_job = JobResponse(
            id=str(j.id),
            celery_id=j.celery_id,
            status=j.status.value,
            started_at=j.started_at.isoformat() if j.started_at else None,
            finished_at=j.finished_at.isoformat() if j.finished_at else None,
            error_msg=j.error_msg,
        )
    return DocumentResponse(
        id=str(doc.id),
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status.value,
        error_msg=doc.error_msg,
        created_at=doc.created_at.isoformat(),
        latest_job=latest_job,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document and queue it for ingestion",
)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    _validate_file(file)

    # Save file to disk
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    doc_id   = uuid.uuid4()
    ext      = Path(file.filename or "").suffix.lower()
    safe_name = f"{doc_id}{ext}"
    dest_path = upload_dir / safe_name

    file_size = 0
    with open(dest_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):   # 1 MB chunks
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit",
                )
            f.write(chunk)

    # Persist Document record
    doc = Document(
        id=doc_id,
        filename=file.filename or safe_name,
        file_path=str(dest_path),
        file_type=ext.lstrip("."),
        file_size=file_size,
        status=DocumentStatus.PENDING,
    )
    db.add(doc)

    # Create ProcessingJob record
    job = ProcessingJob(document_id=doc_id, status=DocumentStatus.PENDING)
    db.add(job)
    
    # IMPORTANT: Commit before queuing the Celery task to avoid race conditions
    # where the fast 'solo' worker looks up the document before it's saved.
    await db.commit()

    # Queue Celery task
    task = ingest_document.delay(str(doc_id), str(dest_path))

    # Update job with the Celery task ID
    job.celery_id = task.id
    db.add(job)
    await db.commit()

    logger.info("upload.queued", document_id=str(doc_id), celery_task=task.id)

    return UploadResponse(
        document_id=str(doc_id),
        job_id=str(job.id),
        celery_task_id=task.id,
        message="Document received and queued for ingestion.",
    )


@router.get(
    "/",
    response_model=List[DocumentResponse],
    summary="List all documents",
)
async def list_documents(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.jobs))
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    docs = result.scalars().all()
    return [_doc_to_response(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a single document and its job status",
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.jobs))
        .where(Document.id == doc_uuid)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_response(doc)


@router.get(
    "/status/{job_id}",
    response_model=JobResponse,
    summary="Get ingestion job status",
)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_uuid)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return JobResponse(
        id=str(job.id),
        celery_id=job.celery_id,
        status=job.status.value,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        error_msg=job.error_msg,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all its vectors",
)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    result = await db.execute(select(Document).where(Document.id == doc_uuid))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning("delete.file_error", error=str(e))

    # Delete vectors from Qdrant
    try:
        delete_document_vectors(document_id)
    except Exception as e:
        logger.warning("delete.qdrant_error", error=str(e))

    # Delete DB rows (cascade handles chunks + jobs)
    await db.delete(doc)
    await db.commit()
    logger.info("document.deleted", document_id=document_id)
