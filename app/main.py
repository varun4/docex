"""FastAPI application factory with lifespan, middleware, exception handlers, and router registration."""

from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings
from app.enums import ErrorCode
from app.exceptions import AppError
from app.metrics import DB_POOL_SIZE

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: create connections on startup, close on shutdown.

    Initializes asyncpg pool, Redis, Elasticsearch client, and Kafka producer.
    """
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
    """Create and configure the FastAPI application instance.

    Registers middleware, exception handlers (AppError, RequestValidationError, generic),
    and all route routers.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="DocEx",
        version=settings.version,
        lifespan=lifespan,
    )

    from app.middleware import global_rate_limit_middleware
    app.middleware("http")(global_rate_limit_middleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors with a standardized error envelope."""

        from app.metrics import ERRORS
        ERRORS.labels(type=ErrorCode.VALIDATION_ERROR.value).inc()
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": "Validation error",
                    "detail": exc.errors(),
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """Handle known application errors with the standard error envelope."""

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
        """Catch-all handler for unhandled exceptions (returns 500)."""

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

    from app.routers.v1 import documents, health, metrics, search, tenants
    app.include_router(documents.router, prefix="/api/v1/documents")
    app.include_router(search.router, prefix="/api/v1/search")
    app.include_router(health.router, prefix="/api/v1/health")
    app.include_router(metrics.router, prefix="/api/v1/metrics")
    app.include_router(tenants.router, prefix="/api/v1/tenants")

    return app


app = create_app()
