# Progress

## Done
- [x] `SPEC.md` — tech stack, API contracts, DB schema, caching, rate limiting, health check
- [x] `DESIGN.md` — high-level + low-level design (phase plan, file specs, dependency graph)
- [x] `scripts/seed.py` + `data/seed.jsonl` — 2,814 documents from Stardew Valley Wiki
- [x] `scripts/bulk_import.py` — JSONL → API
- [x] `scripts/init_db.py` — idempotent outbox schema creation
- [x] `scripts/init_es.py` — idempotent ES index creation
- [x] `docker-compose.yml` — 6 services (postgres, redis, elasticsearch, kafka, app, consumer)
- [x] `Dockerfile`, `Dockerfile.consumer`, `requirements.txt`, `.env.example`, `README.md`
- [x] `app/enums.py` — ErrorCode enum (NOT_FOUND, RATE_LIMITED, MISSING_TENANT, INTERNAL_ERROR, VALIDATION_ERROR)
- [x] `app/exceptions.py` — AppError using ErrorCode (no raw strings)
- [x] `app/config.py` — Settings via pydantic-settings (rate limits, TTLs, ES/Kafka settings)
- [x] `app/main.py` — FastAPI app factory with lifespan (asyncpg pool, redis, ES client, Kafka producer), AppError + ValidationError + 500 handlers, global rate limit middleware
- [x] `app/dependencies.py` — get_tenant_id, get_db_pool, get_redis, get_elasticsearch, get_kafka_producer, rate_limit() factory (all raise AppError)
- [x] `app/schemas/` — Document, Search, Health, Events Pydantic models (no raw dicts)
- [x] `app/repositories/document_repository.py` — Elasticsearch (index_document, get_by_id, search, delete, ping) returning typed models
- [x] `app/repositories/cache_repository.py` — Redis (doc cache, search cache, ping) with typed serialization
- [x] `app/repositories/outbox_repository.py` — PostgreSQL outbox INSERT/UPDATE/get_pending
- [x] `app/kafka/producer.py` — Async Kafka producer (publish_event with tenant_id key)
- [x] `app/services/document_service.py` — typed CRUD orchestration with outbox + Kafka ingest + cache-aside
- [x] `app/services/search_service.py` — typed search with cache-aside (Redis → ES)
- [x] `app/services/health_service.py` — typed health check (PG, Redis, ES, Kafka) with latency
- [x] `app/routers/documents.py` — POST/GET/DELETE /documents with rate limiting
- [x] `app/routers/search.py` — GET /search with rate limiting
- [x] `app/routers/health.py` — GET /health (no auth, no rate limit)
- [x] `app/middleware.py` — request ID, rate limit headers, metrics, global rate limiter
- [x] `app/metrics.py` — Prometheus counters/histograms (requests, cache ops, errors, pool size)
- [x] `consumer/main.py` — Kafka consumer loop (poll `documents.ingest` → indexer → outbox status update)
- [x] `consumer/indexer.py` — ES indexer + Redis cache warm + outbox status update + search cache invalidation
- [x] Infrastructure: 6 Docker containers orchestrated, all health checks passing
- [x] End-to-end test — all endpoints verified (POST async, GET, search, DELETE, health, 404s, missing tenant, rate limiting)
- [x] Rename repo from `docextract` to `docex` — updated all references

## 🎯 Audit Fixes (Jul 2026)
- [x] Remove dead `check_rate_limit` from cache_repository
- [x] Fix `DocExtract` → `DocEx` in script headers
- [x] Update DESIGN.md (consumer struct, SearchResult, ES replicas=0, LLD signatures, middleware dir)
- [x] Update SPEC.md (remove `id?` from POST body, remove HTTP 401, replicas=0)
- [x] Update PROGRESS.md — remove stale Next section
- [x] Add search flow cache-aside diagram to README.md
- [x] Enforce global rate limit (middleware)
- [x] Invalidate search cache on new document index (consumer)
- [x] Set Kafka partitions to 3 explicitly
- [x] Standard validation error envelope (RequestValidationError handler)
- [x] Document health degraded/unavailable states in SPEC.md
- [x] Replace raw dict DELETE response with Pydantic model
