"""Elasticsearch repository for document CRUD and full-text search operations."""

import uuid

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchResult

settings = Settings()


class DocumentRepository:
    """Provides document-level data access against Elasticsearch."""

    def __init__(self, es: AsyncElasticsearch):
        """Initialize with an Elasticsearch client.

        Args:
            es: Async Elasticsearch client.
        """
        self.es = es

    async def index_document(
        self,
        tenant_id: str,
        doc_id: uuid.UUID,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        """Index a document into Elasticsearch.

        Args:
            tenant_id: Tenant namespace.
            doc_id: UUID for the document.
            title: Document title.
            content: Document body text.
            metadata: Optional arbitrary JSON metadata.

        Returns:
            The indexed document body as a dict.
        """
        body = {
            "doc_id": str(doc_id),
            "tenant_id": tenant_id,
            "title": title,
            "content": content,
            "metadata": metadata or {},
        }
        await self.es.index(
            index=settings.es_index_name,
            id=str(doc_id),
            body=body,
            refresh="wait_for",
        )
        return body

    async def get_by_id(
        self,
        tenant_id: str,
        doc_id: uuid.UUID,
    ) -> DocumentResponse | None:
        """Retrieve a document by its id, scoped to the given tenant.

        Args:
            tenant_id: Tenant namespace for access control.
            doc_id: UUID of the document.

        Returns:
            DocumentResponse if found and owned by tenant, else None.
        """
        try:
            result = await self.es.get(
                index=settings.es_index_name,
                id=str(doc_id),
            )
        except Exception:
            return None

        source = result["_source"]
        if source.get("tenant_id") != tenant_id:
            return None

        return DocumentResponse.model_validate({
            "id": doc_id,
            "title": source["title"],
            "content": source["content"],
            "metadata": source.get("metadata", {}),
            "created_at": source.get("created_at"),
            "updated_at": source.get("updated_at"),
        })

    async def delete(
        self,
        tenant_id: str,
        doc_id: uuid.UUID,
    ) -> bool:
        """Delete a document from Elasticsearch, scoped to the given tenant.

        Args:
            tenant_id: Tenant namespace.
            doc_id: UUID of the document to delete.

        Returns:
            True if the document was found and deleted, False otherwise.
        """
        try:
            doc = await self.es.get(
                index=settings.es_index_name,
                id=str(doc_id),
            )
        except Exception:
            return False

        source = doc["_source"]
        if source.get("tenant_id") != tenant_id:
            return False

        await self.es.delete(
            index=settings.es_index_name,
            id=str(doc_id),
            refresh="wait_for",
        )
        return True

    async def find_by_hash(
        self,
        tenant_id: str,
        content_hash: str,
    ) -> DocumentResponse | None:
        """Look up a document by its content hash.

        Args:
            tenant_id: Tenant namespace filter.
            content_hash: SHA256 hex digest.

        Returns:
            DocumentResponse if found, else None.
        """
        result = await self.es.search(
            index=settings.es_index_name,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"tenant_id": tenant_id}},
                            {"term": {"content_hash": content_hash}},
                        ]
                    }
                },
                "size": 1,
            },
        )
        hits = result["hits"]["hits"]
        if not hits:
            return None
        source = hits[0]["_source"]
        return DocumentResponse.model_validate({
            "id": source["doc_id"],
            "title": source["title"],
            "content": source["content"],
            "metadata": source.get("metadata", {}),
            "created_at": source.get("created_at"),
            "updated_at": source.get("updated_at"),
        })

    async def search(
        self,
        tenant_id: str,
        query: str,
        from_: int,
        size: int,
    ) -> tuple[list[SearchResult], int]:
        """Full-text search across documents, scoped by tenant.

        Uses multi_match with title^2 boost, title.keyword^3 for exact
        matches, and most_fields type to sum scores across fields.

        Args:
            tenant_id: Tenant namespace filter.
            query: Free-text search string.
            from_: Offset for pagination.
            size: Number of results to return.

        Returns:
            A tuple of (list of SearchResult, total hit count).
        """
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"tenant_id": tenant_id}},
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^2", "title.keyword^3", "content"],
                                "type": "most_fields",
                            }
                        },
                    ]
                }
            },
            "from": from_,
            "size": size,
        }

        result = await self.es.search(
            index=settings.es_index_name,
            body=body,
        )

        total = result["hits"]["total"]["value"]
        results = [
            SearchResult(
                id=hit["_source"]["doc_id"],
                title=hit["_source"]["title"],
                rank=hit["_score"],
            )
            for hit in result["hits"]["hits"]
        ]
        return results, total

    async def get_tenants(
            self
    ) -> list[str]:
        body = {
            "size": 0,
            "aggs": {
                "unique_tenants": {
                    "terms": {
                        "field": "tenant_id",
                    }
                }
            }
        }
        result = await self.es.search(
            index=settings.es_index_name,
            body=body,
        )

        buckets = result["aggregations"]["unique_tenants"]["buckets"]
        tenants = [bucket["key"] for bucket in buckets]
        return tenants

    async def ping(self) -> bool:
        """Check Elasticsearch connectivity.

        Returns:
            True if ES responds to ping, False otherwise.
        """
        try:
            return await self.es.ping()
        except Exception:
            return False
