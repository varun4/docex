"""ASGI middleware for global rate limiting, request ID injection, rate limit headers, and Prometheus metrics."""

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.enums import ErrorCode
from app.metrics import REQUESTS, REQUEST_DURATION

settings = Settings()

SKIP_GLOBAL_RATE_LIMIT = {"/api/v1/health", "/api/v1/metrics"}


async def global_rate_limit_middleware(request: Request, call_next):
    """Enforce a global rate limit (req/s) across all tenants before processing the request.

    Skips /api/v1/health and /api/v1/metrics endpoints. Passes through to request_id_middleware.
    """
    if request.url.path not in SKIP_GLOBAL_RATE_LIMIT:
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            key = "ratelimit:global"
            now_ms = int(time.time() * 1000)
            member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

            pipe = redis.pipeline()
            pipe.zadd(key, {member: now_ms})
            pipe.zremrangebyscore(key, 0, now_ms - settings.rate_limit_window_ms)
            pipe.zcard(key)
            pipe.expire(key, settings.rate_limit_redis_ttl)
            results = await pipe.execute()

            count = results[2]
            if count > settings.rate_limit_global:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": ErrorCode.RATE_LIMITED.value,
                            "message": "Too many requests",
                            "detail": f"Global rate limit of {settings.rate_limit_global} req/s exceeded",
                        }
                    },
                )

    return await request_id_middleware(request, call_next)


async def request_id_middleware(request: Request, call_next):
    """Inject X-Request-ID, rate limit headers, and collect Prometheus request metrics.

    Args:
        request: The incoming HTTP request.
        call_next: The next middleware or route handler.

    Returns:
        Response with added headers for request ID and rate limit info.
    """
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
