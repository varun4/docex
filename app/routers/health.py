from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.dependencies import get_db_pool, get_redis
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["health"])


def get_health_service(
    db_pool=Depends(get_db_pool),
    redis=Depends(get_redis),
) -> HealthService:
    return HealthService(db_pool, redis)


@router.get("", response_model=HealthResponse)
async def health_check(svc=Depends(get_health_service)):
    result = await svc.check()
    status_code = 200 if result.status == "healthy" else 503
    return JSONResponse(content=result.model_dump(), status_code=status_code)
