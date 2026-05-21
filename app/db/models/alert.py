"""
app/db/models/alert.py
SQLAlchemy model for Action Agent alerts (anomalies, contradictions, missing clauses).
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class AlertSeverity(str, enum.Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(String(255), nullable=True, index=True)
    document_id = Column(String(255), nullable=True, index=True)  # pipe-separated for multi-doc
    alert_type  = Column(String(100), nullable=False)             # "anomaly" | "contradiction" | "missing_clause"
    message     = Column(Text, nullable=False)
    severity    = Column(
        Enum(AlertSeverity, name="alert_severity"),
        nullable=False,
        default=AlertSeverity.MEDIUM,
    )
    context     = Column(Text, nullable=True)                     # relevant chunk text
    created_at  = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id":          str(self.id),
            "session_id":  self.session_id,
            "document_id": self.document_id,
            "alert_type":  self.alert_type,
            "message":     self.message,
            "severity":    self.severity.value,
            "context":     self.context,
            "created_at":  self.created_at.isoformat(),
        }
