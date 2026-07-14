import time

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.repositories.document_repository import DocumentRepository
from app.schemas.health import DependencyStatus, HealthResponse

settings = Settings()


class HealthService:
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis: aioredis.Redis,
        es: AsyncElasticsearch,
        kafka_producer: AIOKafkaProducer,
        doc_repo: DocumentRepository | None = None,
    ):
        self.db_pool = db_pool
        self.redis = redis
        self.es = es
        self.kafka_producer = kafka_producer
        self.doc_repo = doc_repo or DocumentRepository(es)

    async def check(self) -> HealthResponse:
        pg_ok, pg_latency = await self._check_postgres()
        redis_ok, redis_latency = await self._check_redis()
        es_ok, es_latency = await self._check_elasticsearch()
        kafka_ok, kafka_latency = await self._check_kafka()

        deps = {
            "postgres": DependencyStatus(
                status="up" if pg_ok else "down", latency_ms=pg_latency
            ),
            "redis": DependencyStatus(
                status="up" if redis_ok else "down", latency_ms=redis_latency
            ),
            "elasticsearch": DependencyStatus(
                status="up" if es_ok else "down", latency_ms=es_latency
            ),
            "kafka": DependencyStatus(
                status="up" if kafka_ok else "down", latency_ms=kafka_latency
            ),
        }

        all_up = pg_ok and redis_ok and es_ok and kafka_ok
        any_up = pg_ok or redis_ok or es_ok or kafka_ok

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

    async def _check_elasticsearch(self) -> tuple[bool, float | None]:
        try:
            start = time.monotonic()
            ok = await self.doc_repo.ping()
            latency = (time.monotonic() - start) * 1000
            return ok, round(latency, 1)
        except Exception:
            return False, None

    async def _check_kafka(self) -> tuple[bool, float | None]:
        try:
            start = time.monotonic()
            await self.kafka_producer.client.force_metadata_update()
            latency = (time.monotonic() - start) * 1000
            return True, round(latency, 1)
        except Exception:
            return False, None
