"""Indexes a Kafka document event into Elasticsearch, warms Redis cache, and updates outbox status."""

import logging

import asyncpg
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.enums import EventStatus, EventType
from app.repositories.document_repository import DocumentRepository
from app.repositories.hash_utils import compute_content_hash
from app.schemas.documents import DocumentResponse
from app.schemas.events import DocumentEvent
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
        self.doc_repo = DocumentRepository(es)

    async def process_event(self, event_data: dict):
        """Process a single document event from Kafka.

        For EventType.DELETE, removes the document from ES.
        For all other event types, computes content hash, checks ES for an
        identical existing document (idempotency), and either:
          - marks the event as 'duplicate' if content already exists, or
          - indexes into ES, warms the doc cache, invalidates the
            tenant's search cache, and marks the event as 'completed'.
        On failure, marks as EventStatus.FAILED.

        Args:
            event_data: Deserialized Kafka message payload as a dict.
        """
        event = DocumentEvent.model_validate(event_data)

        try:
            if event.event_type is EventType.DELETE:
                await self.es.delete(
                    index=settings.es_index_name,
                    id=str(event.doc_id),
                    ignore=[404],
                )

                async with self.pg_pool.acquire() as conn:
                    await self.outbox_repo.update_status(conn, event.event_id, EventStatus.COMPLETED)
                log.info("Deleted doc %s (event %s)", event.doc_id, event.event_id)
                return

            content_hash = compute_content_hash(event.tenant_id, event.title, event.content)
            existing = await self.doc_repo.find_by_hash(event.tenant_id, content_hash)

            if existing:
                async with self.pg_pool.acquire() as conn:
                    await self.outbox_repo.update_status(
                        conn, event.event_id, EventStatus.DUPLICATE,
                        f"duplicate of existing document {existing.id}",
                    )
                log.info("Duplicate doc %s skipped (event %s)", event.doc_id, event.event_id)
                return

            body = {
                "doc_id": str(event.doc_id),
                "tenant_id": event.tenant_id,
                "content_hash": content_hash,
                "title": event.title,
                "content": event.content,
                "metadata": event.metadata,
                "created_at": event.timestamp.isoformat(),
                "updated_at": event.timestamp.isoformat(),
            }
            await self.es.index(
                index=settings.es_index_name,
                id=str(event.doc_id),
                body=body,
            )

            doc_response = DocumentResponse(
                id=event.doc_id,
                title=event.title,
                content=event.content,
                metadata=event.metadata,
                created_at=event.timestamp,
                updated_at=event.timestamp,
            )
            await self.redis.setex(
                f"doc:{event.tenant_id}:{event.doc_id}",
                settings.cache_ttl_doc,
                doc_response.model_dump_json(),
            )

            cursor = 0
            pattern = f"search:{event.tenant_id}:*"
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=settings.cache_scan_count)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break

            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event.event_id, EventStatus.COMPLETED)

            log.info("Processed event %s (%s) for doc %s", event.event_id, event.event_type.value, event.doc_id)

        except Exception as e:
            log.error("Failed to process event %s: %s", event.event_id, e)
            async with self.pg_pool.acquire() as conn:
                await self.outbox_repo.update_status(conn, event.event_id, EventStatus.FAILED, str(e))
