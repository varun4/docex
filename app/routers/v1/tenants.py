from fastapi import APIRouter, Depends

from app.config import Settings
from app.dependencies import get_elasticsearch
from app.repositories.document_repository import DocumentRepository
from app.schemas.tenant import TenantResponse
from app.services.tenant_service import TenantService

router = APIRouter(tags=["tenants"])
settings = Settings()

def get_tenant_service(
    es=Depends(get_elasticsearch),
) -> TenantService:
    """Dependency factory that wires up TenantService."""
    return TenantService(es, DocumentRepository(es))

@router.get("", response_model=TenantResponse)
async def get_tenants(svc=Depends(get_tenant_service),):
    return await svc.get_tenants()
