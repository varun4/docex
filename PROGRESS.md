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
- [x] `app/main.py` — all routers wired in, full OpenAPI spec (5 endpoints)
- [x] End-to-end test — all 5 endpoints verified (CRUD, search, health, 404s, rate limiting)
- [x] Rename repo from `docextract` to `docex` — updated all `docsextract` references in project files
- [x] Search ranking fix — weighted tsvector (setweight A/B), explicit rank weights `{0.05,0.05,0.05,1.0}`, normalization=0, websearch_to_tsquery
- [x] Redirect page filter — seed.py startswith("REDIRECT"), search-time `NOT content ILIKE 'REDIRECT%'`, 809 purge from DB
- [x] Makefile start/stop targets — PID-tracked lifecycle with stale process cleanup

## 🎯 Design Changes (Jul 2026)
- [x] Architecture redesign: PG → outbox only, ES as doc store + search, Kafka event bus
- [x] `DESIGN.md` — updated architecture diagram, data flows, outbox schema, ES mapping, Kafka event model, project structure, LLD
- [x] `SPEC.md` — updated tech stack, architecture, API contracts, outbox schema, ES mapping, Kafka topics, health check

## Next
- [ ] Port `app/main.py` — add ES client, Kafka producer, remove PG FTS
- [ ] Port `app/dependencies.py` — add get_elasticsearch, get_kafka_producer deps
- [ ] Port `app/config.py` — add ES, Kafka, outbox settings
- [ ] Create `app/schemas/events.py` — DocumentEvent model
- [ ] Create `app/repositories/outbox_repository.py` — PG outbox INSERT/UPDATE
- [ ] Rewrite `app/repositories/document_repository.py` — ES queries instead of PG FTS
- [ ] Rewrite `app/services/document_service.py` — async ingest via outbox + Kafka
- [ ] Rewrite `app/services/search_service.py` — ES search instead of PG FTS
- [ ] Create `app/kafka/producer.py` — async Kafka producer
- [ ] Create `consumer/` package — Kafka consumer + ES indexer
- [ ] Update `docker-compose.yml` — add ES, Kafka, consumer services
- [ ] Create `Dockerfile.consumer` — consumer image
- [ ] Update `scripts/seed.py` — seed ES from jsonl
- [ ] Create `scripts/init_es.py` — ES index creation
- [ ] Update `.env.example` — add ES, Kafka settings
- [ ] End-to-end test with new architecture
