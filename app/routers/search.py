"""REST endpoint for full-text search: GET /search."""

from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.dependencies import get_elasticsearch, get_redis, get_tenant_id, rate_limit
from app.repositories.cache_repository import CacheRepository
from app.schemas.search import SearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])
settings = Settings()


def get_search_service(
    es=Depends(get_elasticsearch),
    redis=Depends(get_redis),
) -> SearchService:
    """Dependency factory that wires up SearchService."""
    return SearchService(es, CacheRepository(redis))


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    page: int = Query(settings.search_default_page, ge=1),
    size: int = Query(settings.search_default_size, ge=1, le=settings.search_max_size),
    tenant_id=Depends(get_tenant_id),
    _=Depends(rate_limit("search", settings.rate_limit_search)),
    svc=Depends(get_search_service),
):
    """Full-text search across tenant-scoped documents with pagination.

    Results are cached in Redis with a configurable TTL (default 60s).
    """
    return await svc.search(tenant_id, q, page, size)
