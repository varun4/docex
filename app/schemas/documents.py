from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str
    content: str
    metadata: dict | None = None


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    content: str
    metadata: dict = {}
    created_at: datetime
    updated_at: datetime


class IngestResponse(BaseModel):
    id: UUID
    event_id: UUID
    status: str = "pending"


class DeleteResponse(BaseModel):
    status: str
