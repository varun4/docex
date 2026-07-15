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
- [x] `app/routers/v1/documents.py` — POST/GET/DELETE /api/v1/documents with rate limiting
- [x] `app/routers/v1/search.py` — GET /api/v1/search with rate limiting
- [x] `app/routers/v1/health.py` — GET /api/v1/health (no auth, no rate limit)
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

## 🎯 Housekeeping Fixes (Jul 2026)
- [x] Add missing deps to `pyproject.toml` — `elasticsearch[async]`, `aiokafka`, `prometheus-client`
- [x] Fix `.env` DB name — `docsextract` → `docex`

## 🎯 API Versioning (Jul 2026)
- [x] Move routers into versioned module: `app/routers/` → `app/routers/v1/` (documents, search, health, metrics)
- [x] Register all routes under `/api/v1/` prefix via `app.include_router(prefix=...)` in `main.py`
- [x] Update Caddyfile path matching, UI fetch paths, scripts, and all docs to reflect `/api/v1/` prefix
- [x] Version is now purely a routing concern — adding v2 means creating `app/routers/v2/` and registering alongside v1

## 🎯 Caddy Entry Point & FQDN Support (Jul 2026)
- [x] Remove direct app port exposure (`ports: 8000:8000` removed from `docker-compose.yml`)
- [x] Change Caddy defaults to standard ports (`80:80`, `443:443`)
- [x] Caddyfile has `:80` block (local dev / fallback); deploy appends domain block for FQDN HTTPS
- [x] Remove stale `{$DOMAIN}` from Caddyfile (Caddy v2 treats empty env var as global options block, causes error)
- [x] Deploy script appends domain block with correct `/api/v1/` paths (idempotent — checks for existing block)
- [x] Remove DOMAIN from docker-compose caddy environment (domain is hardcoded in Caddyfile appended block)
- [x] All docs and deploy script updated to use port 80 and `/api/v1/` paths
- [x] Single entry point: everything goes through Caddy on port 80/443
- [x] End-to-end verified — all 9 endpoints pass through Caddy proxy
- [x] deploy.sh now sources `.env` for DOMAIN/EMAIL — can set them in .env or pass via CLI (CLI overrides .env)
- [x] README.md — scripts section converted to proper Markdown table with "Run via" and "Key flags" columns
- [x] DEMO.md — comprehensive demo covering health, ingest, retrieval, search, delete, multi-tenancy, rate limiting, errors, metrics, and web UI
- [x] Add `EventStatus` enum to `app/enums.py` (PENDING, COMPLETED, FAILED)
- [x] Replace all hardcoded event status strings with `EventStatus` enum across schemas, services, repositories, and consumer
- [x] Add `GET /api/v1/documents/events/{event_id}` endpoint with tenant-isolated event status tracking
- [x] Add `get_event_by_id` to OutboxRepository and `get_event_status` to DocumentService
- [x] Document event tracking in DEMO.md and SPEC.md
