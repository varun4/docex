import time
import uuid

from fastapi import Depends, Header, Request

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError

settings = Settings()


async def get_tenant_id(x_tenant_id: str = Header(None)) -> str:
    if not x_tenant_id:
        raise AppError(
            ErrorCode.MISSING_TENANT,
            "Missing tenant",
            "X-Tenant-ID header is required",
            400,
        )
    return x_tenant_id


async def get_db_pool(request: Request):
    return request.app.state.db_pool


async def get_redis(request: Request):
    return request.app.state.redis


async def get_elasticsearch(request: Request):
    return request.app.state.es


async def get_kafka_producer(request: Request):
    return request.app.state.kafka_producer


def rate_limit(group: str, max_rps: int):
    async def check(
        redis=Depends(get_redis),
        tenant_id=Depends(get_tenant_id),
        request: Request = None,
    ):
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
