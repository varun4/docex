# Progress

## Done
- [x] `SPEC.md` — tech stack, API contracts, DB schema, caching, rate limiting
- [x] `DESIGN.md` — high-level + low-level design (phase plan, file specs, dependency graph)
- [x] `scripts/seed.py` + `data/seed.jsonl` — 2,814 documents from Stardew Valley Wiki
- [x] `scripts/bulk_import.py` — JSONL → API or direct DB (--db-url)
- [x] `scripts/init_db.py` — idempotent schema creation
- [x] `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`, `Makefile`, `README.md`
- [x] `app/enums.py` — ErrorCode enum (NOT_FOUND, RATE_LIMITED, MISSING_TENANT, INTERNAL_ERROR, VALIDATION_ERROR)
- [x] `app/exceptions.py` — AppError using ErrorCode (no raw strings)
- [x] `app/config.py` — Settings via pydantic-settings
- [x] `app/main.py` — FastAPI app factory with lifespan (asyncpg pool + redis), AppError + 500 handlers
- [x] `app/dependencies.py` — get_tenant_id, get_db_pool, get_redis, rate_limit() factory (all raise AppError)
- [x] `app/schemas/` — Common, Document, Search, Health Pydantic models (no raw dicts)
- [x] `app/repositories/document_repository.py` — PostgreSQL (create, get_by_id, delete, search) returning typed models
- [x] `app/repositories/cache_repository.py` — Redis (doc cache, search cache, rate limiter, ping) with typed serialization
- [x] `app/services/document_service.py` — typed CRUD orchestration with cache-aside
- [x] `app/services/search_service.py` — typed search with cache-aside
- [x] `app/services/health_service.py` — typed health check with latency measurement
- [x] `app/routers/documents.py` — POST/GET/DELETE /documents with rate limiting
- [x] `app/routers/search.py` — GET /search with rate limiting
- [x] `app/routers/health.py` — GET /health (no auth, no rate limit)
- [x] `app/routers/documents.py` — POST/GET/DELETE /documents with rate limiting
- [x] `app/routers/search.py` — GET /search with rate limiting
- [x] `app/routers/health.py` — GET /health (no auth, no rate limit)
- [x] `app/main.py` — all routers wired in, full OpenAPI spec (5 endpoints)
- [x] End-to-end test — all 5 endpoints verified (CRUD, search, health, 404s, rate limiting)
- [x] Rename repo from `docextract` to `docex` — updated all `docsextract` references in project files
