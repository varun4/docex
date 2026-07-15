"""REST endpoint for health check: GET /api/v1/health."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.dependencies import get_db_pool, get_elasticsearch, get_kafka_producer, get_redis
from app.repositories.cache_repository import CacheRepository
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


def get_health_service(
    db_pool=Depends(get_db_pool),
    redis=Depends(get_redis),
    es=Depends(get_elasticsearch),
    kafka_producer=Depends(get_kafka_producer),
) -> HealthService:
    """Dependency factory that wires up HealthService."""
    return HealthService(db_pool, redis, es, kafka_producer)


@router.get("", response_model=HealthResponse)
async def health_check(svc=Depends(get_health_service)):
    """Check the health of all external dependencies.

    Returns 200 with status 'healthy' when all deps are up,
    503 with 'degraded' (some up) or 'unavailable' (none up).
    """
    result = await svc.check()
    status_code = 200 if result.status == "healthy" else 503
    return JSONResponse(content=result.model_dump(), status_code=status_code)
