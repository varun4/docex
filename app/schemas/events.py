"""Kafka event model for document ingest messages."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentEvent(BaseModel):
    """Event published to the `documents.ingest` Kafka topic for async processing."""

    event_id: UUID
    event_type: str  # 'create', 'update', 'delete'
    tenant_id: str
    doc_id: UUID
    title: str
    content: str
    metadata: dict = {}
    timestamp: datetime
