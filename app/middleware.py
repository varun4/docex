import time
import uuid

from fastapi import Request

from app.metrics import REQUESTS, REQUEST_DURATION


async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
    request.state.request_id = request_id

    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start

    response.headers["X-Request-ID"] = request_id

    rate_limit_info = getattr(request.state, "rate_limit_info", None)
    if rate_limit_info:
        response.headers["X-RateLimit-Limit"] = str(rate_limit_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_limit_info["remaining"])

    REQUESTS.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    return response
