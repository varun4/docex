"""Kafka event model for document ingest messages and event status responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.enums import EventStatus


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


class EventStatusResponse(BaseModel):
    """Response returned when checking the processing status of an ingest event."""

    event_id: UUID
    status: EventStatus
    error: str | None = None
