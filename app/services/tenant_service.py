from elasticsearch import AsyncElasticsearch

from app.config import Settings

from app.repositories.document_repository import DocumentRepository
from app.schemas.tenant import TenantResponse

settings = Settings()


class TenantService:
    """Util functions that are not part of a particular entity."""

    def __init__(
        self,
        es: AsyncElasticsearch,
        doc_repo: DocumentRepository | None = None,
    ):
        self.es = es
        self.doc_repo = doc_repo or DocumentRepository(es)

    async def get_tenants(self) -> TenantResponse:
        tenants = await self.doc_repo.get_tenants()
        response = TenantResponse(tenants=tenants)
        return response
