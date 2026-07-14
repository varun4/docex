"""Business logic for full-text search with cache-aside (Redis → ES)."""

import hashlib

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.metrics import CACHE_OPS
from app.repositories.cache_repository import CacheRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.search import SearchResponse

settings = Settings()


class SearchService:
    """Orchestrates full-text search with cache-aside and pagination."""

    def __init__(
        self,
        es: AsyncElasticsearch,
        cache: CacheRepository,
        doc_repo: DocumentRepository | None = None,
    ):
        """Initialize with dependencies.

        Args:
            es: Async Elasticsearch client.
            cache: Redis cache repository.
            doc_repo: Repository for ES search queries (default: new instance).
        """
        self.es = es
        self.cache = cache
        self.doc_repo = doc_repo or DocumentRepository(es)

    async def search(
        self,
        tenant_id: str,
        query: str,
        page: int = 1,
        size: int = 20,
    ) -> SearchResponse:
        """Execute a full-text search with cache-aside (check Redis first, then ES).

        Args:
            tenant_id: Tenant namespace filter.
            query: Free-text search query.
            page: Page number (1-indexed, default 1).
            size: Results per page (default 20, capped by settings.search_max_size).

        Returns:
            SearchResponse with results, total count, and pagination metadata.
        """
        key_hash = hashlib.md5(f"{query}:{page}:{size}".encode()).hexdigest()

        cached = await self.cache.get_search_results(tenant_id, key_hash)
        if cached:
            CACHE_OPS.labels(operation="hit", type="search").inc()
            return cached
        CACHE_OPS.labels(operation="miss", type="search").inc()

        limit = min(size, settings.search_max_size)
        offset = (page - 1) * limit

        results, total = await self.doc_repo.search(tenant_id, query, offset, limit)

        response = SearchResponse(results=results, total=total, page=page, size=limit)
        await self.cache.set_search_results(tenant_id, key_hash, response, settings.cache_ttl_search)
        return response
