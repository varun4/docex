"""Business logic for document CRUD operations with async ingest via outbox + Kafka."""

import uuid
from datetime import datetime, timezone

import asyncpg
from aiokafka import AIOKafkaProducer
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError
from app.kafka.producer import publish_event
from app.metrics import CACHE_OPS
from app.repositories.cache_repository import CacheRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.documents import DocumentResponse, IngestResponse
from app.schemas.events import DocumentEvent

settings = Settings()


class DocumentService:
    """Orchestrates document create, get, and delete with outbox, Kafka, ES, and cache."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        es: AsyncElasticsearch,
        cache: CacheRepository,
        kafka_producer: AIOKafkaProducer,
        outbox_repo: OutboxRepository | None = None,
        doc_repo: DocumentRepository | None = None,
    ):
        """Initialize with dependencies.

        Args:
            db_pool: asyncpg connection pool for outbox writes.
            es: Async Elasticsearch client.
            cache: Redis cache repository.
            kafka_producer: AIOKafka producer for event publishing.
            outbox_repo: Repository for outbox operations (default: new instance).
            doc_repo: Repository for ES document operations (default: new instance).
        """
        self.db_pool = db_pool
        self.es = es
        self.cache = cache
        self.kafka_producer = kafka_producer
        self.outbox_repo = outbox_repo or OutboxRepository()
        self.doc_repo = doc_repo or DocumentRepository(es)

    async def create(
        self,
        tenant_id: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> IngestResponse:
        """Create a document via async ingest pipeline.

        Writes to the PG outbox, publishes a Kafka event, and returns immediately.

        Args:
            tenant_id: Tenant namespace.
            title: Document title.
            content: Document body text.
            metadata: Optional arbitrary JSON metadata.

        Returns:
            IngestResponse with status 'pending' and the event_id for tracking.
        """
        doc_id = uuid.uuid4()

        async with self.db_pool.acquire() as conn:
            event = await self.outbox_repo.insert_event(
                conn, tenant_id, title, content, metadata, doc_id, "create",
            )

        await publish_event(self.kafka_producer, settings.kafka_topic, event)

        return IngestResponse(id=doc_id, event_id=event.event_id, status="pending")

    async def get(self, tenant_id: str, doc_id: str) -> DocumentResponse:
        """Retrieve a document by id with cache-aside (Redis → ES).

        Args:
            tenant_id: Tenant namespace.
            doc_id: Document UUID string.

        Returns:
            DocumentResponse from cache or ES.

        Raises:
            AppError: 404 if the document is not found.
        """
        cached = await self.cache.get_document(tenant_id, doc_id)
        if cached:
            CACHE_OPS.labels(operation="hit", type="document").inc()
            return cached
        CACHE_OPS.labels(operation="miss", type="document").inc()

        doc = await self.doc_repo.get_by_id(tenant_id, uuid.UUID(doc_id))

        if not doc:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Document not found",
                f"No document with id {doc_id}",
                404,
            )

        await self.cache.set_document(tenant_id, doc_id, doc, settings.cache_ttl_doc)
        return doc

    async def delete(self, tenant_id: str, doc_id: str) -> None:
        """Delete a document from ES and evict cache entries.

        Args:
            tenant_id: Tenant namespace.
            doc_id: Document UUID string.

        Raises:
            AppError: 404 if the document is not found.
        """
        deleted = await self.doc_repo.delete(tenant_id, uuid.UUID(doc_id))

        if not deleted:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Document not found",
                f"No document with id {doc_id}",
                404,
            )

        await self.cache.delete_document(tenant_id, doc_id)
        await self.cache.invalidate_search_cache(tenant_id)
