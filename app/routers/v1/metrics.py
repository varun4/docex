"""Prometheus metrics endpoint: GET /api/v1/metrics."""

from fastapi import APIRouter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["metrics"], include_in_schema=False)


@router.get("")
async def metrics():
    """Expose Prometheus metrics in text format."""
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
