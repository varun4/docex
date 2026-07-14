import uuid

import asyncpg

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError
from app.metrics import CACHE_OPS
from app.repositories.cache_repository import CacheRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.documents import DocumentResponse

settings = Settings()


class DocumentService:
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        cache: CacheRepository,
        doc_repo: DocumentRepository | None = None,
    ):
        self.db_pool = db_pool
        self.cache = cache
        self.doc_repo = doc_repo or DocumentRepository()

    async def create(
        self,
        tenant_id: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> DocumentResponse:
        async with self.db_pool.acquire() as conn:
            doc = await self.doc_repo.create(conn, tenant_id, title, content, metadata)
        await self.cache.invalidate_search_cache(tenant_id)
        return doc

    async def create_bulk(
        self,
        tenant_id: str,
        documents: list[tuple[str, str, dict | None]],
    ) -> list[DocumentResponse]:
        results = []
        async with self.db_pool.acquire() as conn:
            for title, content, metadata in documents:
                doc = await self.doc_repo.create(conn, tenant_id, title, content, metadata)
                results.append(doc)
        await self.cache.invalidate_search_cache(tenant_id)
        return results

    async def get(self, tenant_id: str, doc_id: str) -> DocumentResponse:
        cached = await self.cache.get_document(tenant_id, doc_id)
        if cached:
            CACHE_OPS.labels(operation="hit", type="document").inc()
            return cached
        CACHE_OPS.labels(operation="miss", type="document").inc()

        async with self.db_pool.acquire() as conn:
            doc = await self.doc_repo.get_by_id(conn, tenant_id, uuid.UUID(doc_id))

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
        async with self.db_pool.acquire() as conn:
            deleted = await self.doc_repo.delete(conn, tenant_id, uuid.UUID(doc_id))

        if not deleted:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Document not found",
                f"No document with id {doc_id}",
                404,
            )

        await self.cache.delete_document(tenant_id, doc_id)
        await self.cache.invalidate_search_cache(tenant_id)
