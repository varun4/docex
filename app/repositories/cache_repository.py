"""Redis-backed cache repository for document detail and search result caching."""

import json

import redis.asyncio as aioredis

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchResponse

settings = Settings()


class CacheRepository:
    """Provides cache-aside access to Redis for document details and search results."""

    def __init__(self, redis: aioredis.Redis):
        """Initialize with a Redis client instance.

        Args:
            redis: Async Redis client from aioredis.
        """
        self.redis = redis

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentResponse | None:
        """Retrieve a cached document by tenant and document id.

        Args:
            tenant_id: Tenant namespace.
            doc_id: Document UUID string.

        Returns:
            DocumentResponse if found in cache, else None.
        """
        data = await self.redis.get(f"doc:{tenant_id}:{doc_id}")
        return DocumentResponse.model_validate_json(data) if data else None

    async def set_document(self, tenant_id: str, doc_id: str, doc: DocumentResponse, ttl: int = 300):
        """Cache a document response with a TTL.

        Args:
            tenant_id: Tenant namespace.
            doc_id: Document UUID string.
            doc: The document response to cache.
            ttl: Time-to-live in seconds (default 300).
        """
        await self.redis.setex(f"doc:{tenant_id}:{doc_id}", ttl, doc.model_dump_json())

    async def delete_document(self, tenant_id: str, doc_id: str):
        """Remove a single document from the cache.

        Args:
            tenant_id: Tenant namespace.
            doc_id: Document UUID string.
        """
        await self.redis.delete(f"doc:{tenant_id}:{doc_id}")

    async def get_search_results(self, tenant_id: str, key_hash: str) -> SearchResponse | None:
        """Retrieve cached search results for a tenant and query hash.

        Args:
            tenant_id: Tenant namespace.
            key_hash: MD5 hash of the query, page, and size.

        Returns:
            SearchResponse if found, else None.
        """
        data = await self.redis.get(f"search:{tenant_id}:{key_hash}")
        return SearchResponse.model_validate_json(data) if data else None

    async def set_search_results(self, tenant_id: str, key_hash: str, results: SearchResponse, ttl: int = 60):
        """Cache search results with a TTL.

        Args:
            tenant_id: Tenant namespace.
            key_hash: MD5 hash of the query, page, and size.
            results: The search response to cache.
            ttl: Time-to-live in seconds (default 60).
        """
        await self.redis.setex(f"search:{tenant_id}:{key_hash}", ttl, results.model_dump_json())

    async def invalidate_search_cache(self, tenant_id: str):
        """Scan and delete all cached search results for a given tenant.

        Args:
            tenant_id: Tenant namespace whose search cache to clear.
        """
        cursor = 0
        pattern = f"search:{tenant_id}:*"
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=settings.cache_scan_count)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

    async def ping(self) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis responds to PING, False otherwise.
        """
        try:
            return await self.redis.ping()
        except Exception:
            return False
