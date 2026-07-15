"""PostgreSQL repository for the document event outbox table."""

import json
import uuid
from datetime import datetime, timezone

import asyncpg

from app.enums import EventStatus
from app.schemas.events import DocumentEvent


class OutboxRepository:
    """Provides insert, update, and query operations on the document_events outbox table."""
    async def insert_event(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        title: str,
        content: str,
        metadata: dict | None = None,
        doc_id: uuid.UUID | None = None,
        event_type: str = "create",
    ) -> DocumentEvent:
        """Insert a new event into the outbox table.

        Args:
            conn: An active asyncpg connection (from pool).
            tenant_id: Tenant namespace.
            title: Document title.
            content: Document body text.
            metadata: Optional JSON metadata.
            doc_id: Optional document UUID (generated if None).
            event_type: Type of event (e.g. 'create', 'update', 'delete').

        Returns:
            A DocumentEvent model with the persisted event data.
        """
        event_id = uuid.uuid4()
        row = await conn.fetchrow(
            """
            INSERT INTO document_events (event_id, tenant_id, doc_id, title, content, metadata, event_type)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING event_id, event_type, tenant_id, doc_id, title, content, metadata, created_at
            """,
            event_id,
            tenant_id,
            doc_id or uuid.uuid4(),
            title,
            content,
            json.dumps(metadata or {}),
            event_type,
        )
        data = dict(row)
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return DocumentEvent(
            event_id=data["event_id"],
            event_type=data["event_type"],
            tenant_id=data["tenant_id"],
            doc_id=data["doc_id"],
            title=data["title"],
            content=data["content"],
            metadata=data["metadata"],
            timestamp=data["created_at"].replace(tzinfo=timezone.utc),
        )

    async def update_status(
        self,
        conn: asyncpg.Connection,
        event_id: uuid.UUID,
        status: str,
        error: str | None = None,
    ):
        """Update the processing status of an outbox event.

        Args:
            conn: An active asyncpg connection.
            event_id: UUID of the event to update.
            status: New EventStatus value (COMPLETED or FAILED).
            error: Optional error message if the event failed.
        """
        await conn.execute(
            """
            UPDATE document_events
            SET status = $2, error = $3, processed_at = now()
            WHERE event_id = $1
            """,
            event_id,
            status,
            error,
        )

    async def get_pending_events(
        self,
        conn: asyncpg.Connection,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch pending events for processing, oldest first.

        Args:
            conn: An active asyncpg connection.
            limit: Maximum number of events to return (default 100).

        Returns:
            List of event rows as dicts.
        """
        rows = await conn.fetch(
            """
            SELECT * FROM document_events
            WHERE status = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            EventStatus.PENDING.value,
            limit,
        )
        return [dict(r) for r in rows]

    async def get_event_by_id(
        self,
        conn: asyncpg.Connection,
        event_id: uuid.UUID,
    ) -> dict | None:
        """Fetch a single event by its event_id, returning status and error info.

        Args:
            conn: An active asyncpg connection.
            event_id: UUID of the event to retrieve.

        Returns:
            Event row as a dict, or None if not found.
        """
        row = await conn.fetchrow(
            """
            SELECT event_id, tenant_id, status, error, created_at, processed_at
            FROM document_events
            WHERE event_id = $1
            """,
            event_id,
        )
        return dict(row) if row else None
