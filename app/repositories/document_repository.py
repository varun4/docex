import json
import uuid

import asyncpg

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchResult

settings = Settings()


class DocumentRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> DocumentResponse:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (id, tenant_id, title, content, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, tenant_id, title, content, metadata, created_at, updated_at
            """,
            uuid.uuid4(),
            tenant_id,
            title,
            content,
            json.dumps(metadata or {}),
        )
        data = dict(row)
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return DocumentResponse(**data)

    async def get_by_id(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        doc_id: uuid.UUID,
    ) -> DocumentResponse | None:
        row = await conn.fetchrow(
            """
            SELECT id, tenant_id, title, content, metadata, created_at, updated_at
            FROM documents
            WHERE id = $1 AND tenant_id = $2
            """,
            doc_id,
            tenant_id,
        )
        if row:
            data = dict(row)
            if isinstance(data.get("metadata"), str):
                data["metadata"] = json.loads(data["metadata"])
            return DocumentResponse(**data)
        return None

    async def delete(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        doc_id: uuid.UUID,
    ) -> bool:
        result = await conn.execute(
            "DELETE FROM documents WHERE id = $1 AND tenant_id = $2",
            doc_id,
            tenant_id,
        )
        return result != "DELETE 0"

    async def search(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[SearchResult], int]:
        total = await conn.fetchval(
            """
            SELECT count(*)
            FROM documents
            WHERE tenant_id = $1
              AND search_vector @@ plainto_tsquery($3, $2)
            """,
            tenant_id,
            query,
            settings.fts_language,
        )

        rows = await conn.fetch(
            """
            SELECT id, title, ts_rank(search_vector, plainto_tsquery($3, $2), $4) AS rank
            FROM documents
            WHERE tenant_id = $1
              AND search_vector @@ plainto_tsquery($3, $2)
            ORDER BY rank DESC
            LIMIT $5 OFFSET $6
            """,
            tenant_id,
            query,
            settings.fts_language,
            settings.fts_rank_normalization,
            limit,
            offset,
        )
        return [SearchResult(**dict(r)) for r in rows], total
