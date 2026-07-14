import json
import logging

import asyncpg
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.repositories.outbox_repository import OutboxRepository

log = logging.getLogger("consumer.indexer")
settings = Settings()


class Indexer:
    def __init__(
        self,
        es: AsyncElasticsearch,
        redis: aioredis.Redis,
        pg_pool: asyncpg.Pool,
    ):
        self.es = es
        self.redis = redis
        self.pg_pool = pg_pool
        self.outbox_repo = OutboxRepository()

    async def process_event(self, event_data: dict):
        event_id = event_data.get("event_id")
        event_type = event_data.get("event_type")
        tenant_id = event_data.get("tenant_id")
        doc_id = event_data.get("doc_id")
        title = event_data.get("title")
        content = event_data.get("content")
        metadata = event_data.get("metadata", {})

        try:
            timestamp = event_data.get("timestamp")

            if event_type == "delete":
                await self.es.delete(
                    index=settings.es_index_name,
                    id=doc_id,
                    ignore=[404],
                )
            else:
                body = {
                    "doc_id": doc_id,
                    "tenant_id": tenant_id,
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                await self.es.index(
                    index=settings.es_index_name,
                    id=doc_id,
                    body=body,
                )

            doc_response = DocumentResponse(
                id=doc_id,
                title=title,
                content=content,
                metadata=metadata,
                created_at=timestamp,
                updated_at=timestamp,
            )
            await self.redis.setex(
                f"doc:{tenant_id}:{doc_id}",
                settings.cache_ttl_doc,
                doc_response.model_dump_json(),
            )

            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event_id, "completed")

            log.info("Processed event %s (%s) for doc %s", event_id, event_type, doc_id)

        except Exception as e:
            log.error("Failed to process event %s: %s", event_id, e)
            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event_id, "failed", str(e))
