import time

import asyncpg
import redis.asyncio as aioredis

from app.config import Settings
from app.schemas.health import DependencyStatus, HealthResponse

settings = Settings()


class HealthService:
    def __init__(self, db_pool: asyncpg.Pool, redis: aioredis.Redis):
        self.db_pool = db_pool
        self.redis = redis

    async def check(self) -> HealthResponse:
        pg_ok, pg_latency = await self._check_postgres()
        redis_ok, redis_latency = await self._check_redis()

        deps = {
            "postgres": DependencyStatus(
                status="up" if pg_ok else "down", latency_ms=pg_latency
            ),
            "redis": DependencyStatus(
                status="up" if redis_ok else "down", latency_ms=redis_latency
            ),
        }

        all_up = pg_ok and redis_ok
        any_up = pg_ok or redis_ok

        return HealthResponse(
            status="healthy" if all_up else ("degraded" if any_up else "unavailable"),
            version=settings.version,
            dependencies=deps,
        )

    async def _check_postgres(self) -> tuple[bool, float | None]:
        try:
            start = time.monotonic()
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency = (time.monotonic() - start) * 1000
            return True, round(latency, 1)
        except Exception:
            return False, None

    async def _check_redis(self) -> tuple[bool, float | None]:
        try:
            start = time.monotonic()
            await self.redis.ping()
            latency = (time.monotonic() - start) * 1000
            return True, round(latency, 1)
        except Exception:
            return False, None
