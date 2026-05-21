"""
app/db/models/document.py
SQLAlchemy ORM model for uploaded documents and their processing jobs.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class DocumentStatus(str, PyEnum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class Document(Base):
    __tablename__ = "documents"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename   = Column(String(512), nullable=False)
    file_path  = Column(String(1024), nullable=False)
    file_type  = Column(String(64))                    # pdf, docx, txt, etc.
    file_size  = Column(Integer)                       # bytes
    status     = Column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    error_msg  = Column(Text, nullable=True)
    meta       = Column(JSON, default=dict)            # arbitrary metadata

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    jobs   = relationship("ProcessingJob",  back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document id={self.id} name={self.filename} status={self.status}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text        = Column(Text, nullable=False)
    qdrant_id   = Column(String(64))               # vector ID in Qdrant
    page_number = Column(Integer, nullable=True)
    meta        = Column(JSON, default=dict)

    document    = relationship("Document", back_populates="chunks")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    celery_id   = Column(String(255), nullable=True)   # Celery task UUID
    status      = Column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    error_msg   = Column(Text, nullable=True)
    started_at  = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document    = relationship("Document", back_populates="jobs")
