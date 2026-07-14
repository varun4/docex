import json
import uuid
from datetime import datetime, timezone

import asyncpg

from app.schemas.events import DocumentEvent


class OutboxRepository:
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
        rows = await conn.fetch(
            """
            SELECT * FROM document_events
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]
