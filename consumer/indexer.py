"""Indexes a Kafka document event into Elasticsearch, warms Redis cache, and updates outbox status."""

import json
import logging

import asyncpg
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.repositories.hash_utils import compute_content_hash
from app.schemas.documents import DocumentResponse
from app.repositories.outbox_repository import OutboxRepository

log = logging.getLogger("consumer.indexer")
settings = Settings()


class Indexer:
    """Processes document events from Kafka: ES index/delete, cache warm, outbox status update and search cache invalidation."""
    def __init__(
        self,
        es: AsyncElasticsearch,
        redis: aioredis.Redis,
        pg_pool: asyncpg.Pool,
    ):
        """Initialize with connections to ES, Redis, and PostgreSQL.

        Args:
            es: Async Elasticsearch client for indexing/deleting documents.
            redis: Async Redis client for cache warm.
            pg_pool: asyncpg pool for outbox status updates.
        """
        self.es = es
        self.redis = redis
        self.pg_pool = pg_pool
        self.outbox_repo = OutboxRepository()

    async def process_event(self, event_data: dict):
        """Process a single document event from Kafka.

        For 'delete' events, removes the document from ES.
        For all other events, indexes into ES, warms the doc cache,
        invalidates the tenant's search cache, and marks the outbox
        event as 'completed'. On failure, marks as 'failed'.

        Args:
            event_data: Deserialized Kafka message payload as a dict.
        """
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
                content_hash = compute_content_hash(tenant_id, title, content)
                body = {
                    "doc_id": doc_id,
                    "tenant_id": tenant_id,
                    "content_hash": content_hash,
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

            cursor = 0
            pattern = f"search:{tenant_id}:*"
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=settings.cache_scan_count)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break

            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event_id, "completed")

            log.info("Processed event %s (%s) for doc %s", event_id, event_type, doc_id)

        except Exception as e:
            log.error("Failed to process event %s: %s", event_id, e)
            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event_id, "failed", str(e))
