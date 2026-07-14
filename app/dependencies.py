"""FastAPI dependency injection for tenant ID, service connections, and per-tenant rate limiting."""

import time
import uuid

from fastapi import Depends, Header, Request

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError

settings = Settings()


async def get_tenant_id(x_tenant_id: str = Header(None)) -> str:
    """Extract and validate the X-Tenant-ID header.

    Returns:
        The tenant ID string.

    Raises:
        AppError: 400 if the header is missing.
    """
    if not x_tenant_id:
        raise AppError(
            ErrorCode.MISSING_TENANT,
            "Missing tenant",
            "X-Tenant-ID header is required",
            400,
        )
    return x_tenant_id


async def get_db_pool(request: Request):
    """Retrieve the asyncpg connection pool from application state."""
    return request.app.state.db_pool


async def get_redis(request: Request):
    """Retrieve the async Redis client from application state."""
    return request.app.state.redis


async def get_elasticsearch(request: Request):
    """Retrieve the async Elasticsearch client from application state."""
    return request.app.state.es


async def get_kafka_producer(request: Request):
    """Retrieve the AIOKafka producer from application state."""
    return request.app.state.kafka_producer


def rate_limit(group: str, max_rps: int):
    """Factory returning a FastAPI Depends-compatible callable for per-tenant rate limiting.

    Uses sliding window counter via Redis sorted sets.

    Args:
        group: Rate limit group name (e.g. 'search', 'index').
        max_rps: Maximum requests per second allowed.

    Returns:
        An async callable suitable for use as a FastAPI dependency.
    """
    async def check(
        redis=Depends(get_redis),
        tenant_id=Depends(get_tenant_id),
        request: Request = None,
    ):
        """Check the per-tenant rate limit using a sliding window counter.

        Args:
            redis: Redis client dependency.
            tenant_id: Tenant ID dependency.
            request: The current request (for attaching rate limit headers).

        Raises:
            AppError: 429 if the rate limit is exceeded.
        """
        key = f"ratelimit:{tenant_id}:{group}"
        now_ms = int(time.time() * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        pipe = redis.pipeline()
        pipe.zadd(key, {member: now_ms})
        pipe.zremrangebyscore(key, 0, now_ms - settings.rate_limit_window_ms)
        pipe.zcard(key)
        pipe.expire(key, settings.rate_limit_redis_ttl)
        results = await pipe.execute()

        count = results[2]

        if request is not None:
            request.state.rate_limit_info = {
                "limit": max_rps,
                "remaining": max(0, max_rps - count),
            }

        if count > max_rps:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Too many requests",
                f"Rate limit of {max_rps} req/s exceeded for {group}",
                429,
            )

    return check
