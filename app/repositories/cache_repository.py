import json

import redis.asyncio as aioredis

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchResponse

settings = Settings()


class CacheRepository:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentResponse | None:
        data = await self.redis.get(f"doc:{tenant_id}:{doc_id}")
        return DocumentResponse.model_validate_json(data) if data else None

    async def set_document(self, tenant_id: str, doc_id: str, doc: DocumentResponse, ttl: int = 300):
        await self.redis.setex(f"doc:{tenant_id}:{doc_id}", ttl, doc.model_dump_json())

    async def delete_document(self, tenant_id: str, doc_id: str):
        await self.redis.delete(f"doc:{tenant_id}:{doc_id}")

    async def get_search_results(self, tenant_id: str, key_hash: str) -> SearchResponse | None:
        data = await self.redis.get(f"search:{tenant_id}:{key_hash}")
        return SearchResponse.model_validate_json(data) if data else None

    async def set_search_results(self, tenant_id: str, key_hash: str, results: SearchResponse, ttl: int = 60):
        await self.redis.setex(f"search:{tenant_id}:{key_hash}", ttl, results.model_dump_json())

    async def invalidate_search_cache(self, tenant_id: str):
        cursor = 0
        pattern = f"search:{tenant_id}:*"
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=settings.cache_scan_count)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

    async def ping(self) -> bool:
        try:
            return await self.redis.ping()
        except Exception:
            return False
