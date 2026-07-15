"""REST endpoints for document CRUD: POST/GET/DELETE /api/v1/documents."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import Settings
from app.dependencies import get_db_pool, get_elasticsearch, get_kafka_producer, get_redis, get_tenant_id, rate_limit
from app.repositories.cache_repository import CacheRepository
from app.schemas.documents import DeleteResponse, DocumentCreate, DocumentResponse, IngestResponse
from app.schemas.events import EventStatusResponse
from app.services.document_service import DocumentService

router = APIRouter(tags=["documents"])
settings = Settings()


def get_doc_service(
    db_pool=Depends(get_db_pool),
    es=Depends(get_elasticsearch),
    redis=Depends(get_redis),
    kafka_producer=Depends(get_kafka_producer),
) -> DocumentService:
    """Dependency factory that wires up DocumentService with its dependencies."""
    return DocumentService(db_pool, es, CacheRepository(redis), kafka_producer)


@router.post("", status_code=202)
async def create_document(
    body: DocumentCreate,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("index", settings.rate_limit_index)),
    svc=Depends(get_doc_service),
):
    """Ingest a document asynchronously.

    Always returns 202 with event_id for tracking.  The consumer
    handles hashing, idempotency, and indexing.  Poll
    GET /events/{event_id} to check processing status.
    """
    return await svc.create(tenant_id, body.title, body.content, body.metadata)


@router.get("/events/{event_id}", response_model=EventStatusResponse)
async def get_event_status(
    event_id: UUID,
    tenant_id=Depends(get_tenant_id),
    svc=Depends(get_doc_service),
):
    """Check the processing status of an ingest event.

    Returns the current status (pending, completed, or failed) and an
    optional error message if processing failed.
    """
    return await svc.get_event_status(tenant_id, event_id)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("search", settings.rate_limit_search)),
    svc=Depends(get_doc_service),
):
    """Retrieve a document by its UUID, scoped to the tenant."""
    return await svc.get(tenant_id, str(doc_id))


@router.delete("/{doc_id}", response_model=DeleteResponse, status_code=200)
async def delete_document(
    doc_id: UUID,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("index", settings.rate_limit_index)),
    svc=Depends(get_doc_service),
):
    """Delete a document from Elasticsearch and evict cache entries."""
    await svc.delete(tenant_id, str(doc_id))
    return DeleteResponse(status="deleted")
