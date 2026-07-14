from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import Settings
from app.dependencies import get_db_pool, get_elasticsearch, get_kafka_producer, get_redis, get_tenant_id, rate_limit
from app.repositories.cache_repository import CacheRepository
from app.schemas.documents import DeleteResponse, DocumentCreate, DocumentResponse, IngestResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])
settings = Settings()


def get_doc_service(
    db_pool=Depends(get_db_pool),
    es=Depends(get_elasticsearch),
    redis=Depends(get_redis),
    kafka_producer=Depends(get_kafka_producer),
) -> DocumentService:
    return DocumentService(db_pool, es, CacheRepository(redis), kafka_producer)


@router.post("", response_model=IngestResponse, status_code=202)
async def create_document(
    body: DocumentCreate,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("index", settings.rate_limit_index)),
    svc=Depends(get_doc_service),
):
    return await svc.create(tenant_id, body.title, body.content, body.metadata)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("search", settings.rate_limit_search)),
    svc=Depends(get_doc_service),
):
    return await svc.get(tenant_id, str(doc_id))


@router.delete("/{doc_id}", response_model=DeleteResponse, status_code=200)
async def delete_document(
    doc_id: UUID,
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("index", settings.rate_limit_index)),
    svc=Depends(get_doc_service),
):
    await svc.delete(tenant_id, str(doc_id))
    return DeleteResponse(status="deleted")
