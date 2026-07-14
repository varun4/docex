from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError
from app.metrics import DB_POOL_SIZE

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    DB_POOL_SIZE.set(settings.db_pool_max_size)
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=settings.redis_decode_responses)
    app.state.es = AsyncElasticsearch(settings.elasticsearch_url)
    app.state.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
    )
    await app.state.kafka_producer.start()
    yield
    await app.state.db_pool.close()
    await app.state.redis.close()
    await app.state.es.close()
    await app.state.kafka_producer.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocEx",
        version=settings.version,
        lifespan=lifespan,
    )

    from app.middleware import request_id_middleware
    app.middleware("http")(request_id_middleware)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        from app.metrics import ERRORS
        ERRORS.labels(type=exc.code.value).inc()
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        from app.metrics import ERRORS
        ERRORS.labels(type="unhandled").inc()
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "Internal server error",
                    "detail": str(exc) if settings.debug else "",
                }
            },
        )

    from app.routers import documents, health, metrics, search
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app


app = create_app()
