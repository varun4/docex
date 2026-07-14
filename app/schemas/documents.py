"""Pydantic models for document CRUD request/response payloads."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    """Request body for creating a new document."""

    title: str
    content: str
    metadata: dict | None = None


class DocumentResponse(BaseModel):
    """Full document representation returned by GET and search endpoints."""

    id: UUID
    title: str
    content: str
    metadata: dict = {}
    created_at: datetime
    updated_at: datetime


class IngestResponse(BaseModel):
    """Immediate response returned after an async ingest request."""

    id: UUID
    event_id: UUID
    status: str = "pending"


class DeleteResponse(BaseModel):
    """Confirmation response after a successful document deletion."""

    status: str
