"""Business logic for document CRUD operations with async ingest via outbox + Kafka."""

import uuid
from datetime import datetime, timezone

import asyncpg
from aiokafka import AIOKafkaProducer
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.enums import ErrorCode, EventStatus
from app.exceptions import AppError
from app.kafka.producer import publish_event
from app.metrics import CACHE_OPS
from app.repositories.cache_repository import CacheRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.hash_utils import compute_content_hash
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.documents import DocumentResponse, IngestResponse
from app.schemas.events import DocumentEvent, EventStatusResponse

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
    ) -> IngestResponse | DocumentResponse:
        """Create a document via async ingest pipeline.

        Checks content hash for idempotency — if an identical document
        already exists in ES, returns the existing document without
        creating a new one.  Otherwise writes to the PG outbox, publishes
        a Kafka event, and returns IngestResponse with status 'pending'.

        Args:
            tenant_id: Tenant namespace.
            title: Document title.
            content: Document body text.
            metadata: Optional arbitrary JSON metadata.

        Returns:
            DocumentResponse if the document already exists (idempotent),
            otherwise IngestResponse with status 'pending'.
        """
        content_hash = compute_content_hash(tenant_id, title, content)
        existing = await self.doc_repo.find_by_hash(tenant_id, content_hash)
        if existing:
            return existing

        doc_id = uuid.uuid4()

        async with self.db_pool.acquire() as conn:
            event = await self.outbox_repo.insert_event(
                conn, tenant_id, title, content, metadata, doc_id, "create",
            )

        await publish_event(self.kafka_producer, settings.kafka_topic, event)

        return IngestResponse(id=doc_id, event_id=event.event_id, status=EventStatus.PENDING)

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

    async def get_event_status(self, tenant_id: str, event_id: uuid.UUID) -> EventStatusResponse:
        """Check the processing status of an ingest event.

        Args:
            tenant_id: Tenant namespace for access verification.
            event_id: UUID of the event to check.

        Returns:
            EventStatusResponse with current status and optional error message.

        Raises:
            AppError: 404 if the event is not found or belongs to another tenant.
        """
        async with self.db_pool.acquire() as conn:
            row = await self.outbox_repo.get_event_by_id(conn, event_id)

        if not row or row["tenant_id"] != tenant_id:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Event not found",
                f"No event with id {event_id} for this tenant",
                404,
            )

        return EventStatusResponse(
            event_id=event_id,
            status=EventStatus(row["status"]),
            error=row.get("error"),
        )

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
