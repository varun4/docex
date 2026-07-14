import uuid

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchResult

settings = Settings()


class DocumentRepository:
    def __init__(self, es: AsyncElasticsearch):
        self.es = es

    async def index_document(
        self,
        tenant_id: str,
        doc_id: uuid.UUID,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
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

    async def search(
        self,
        tenant_id: str,
        query: str,
        from_: int,
        size: int,
    ) -> tuple[list[SearchResult], int]:
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"tenant_id": tenant_id}},
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^2", "content"],
                                "type": "best_fields",
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

    async def ping(self) -> bool:
        try:
            return await self.es.ping()
        except Exception:
            return False
