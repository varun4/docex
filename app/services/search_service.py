import hashlib

import asyncpg

from app.config import Settings
from app.metrics import CACHE_OPS
from app.repositories.cache_repository import CacheRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.search import SearchResponse

settings = Settings()


class SearchService:
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        cache: CacheRepository,
        doc_repo: DocumentRepository | None = None,
    ):
        self.db_pool = db_pool
        self.cache = cache
        self.doc_repo = doc_repo or DocumentRepository()

    async def search(
        self,
        tenant_id: str,
        query: str,
        page: int = 1,
        size: int = 20,
    ) -> SearchResponse:
        key_hash = hashlib.md5(f"{query}:{page}:{size}".encode()).hexdigest()

        cached = await self.cache.get_search_results(tenant_id, key_hash)
        if cached:
            CACHE_OPS.labels(operation="hit", type="search").inc()
            return cached
        CACHE_OPS.labels(operation="miss", type="search").inc()

        limit = min(size, settings.search_max_size)
        offset = (page - 1) * limit

        async with self.db_pool.acquire() as conn:
            results, total = await self.doc_repo.search(conn, tenant_id, query, limit, offset)

        response = SearchResponse(results=results, total=total, page=page, size=limit)
        await self.cache.set_search_results(tenant_id, key_hash, response, settings.cache_ttl_search)
        return response
