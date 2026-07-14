# DocEx — High-Level Design

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client / API Consumer                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP (REST)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI Service (:8000)                          │
│  ┌──────────┐  ┌────────────┐  ┌────────────────┐                   │
│  │  Router   │→ │  Service   │→ │  Repository     │                   │
│  │   Layer   │  │   Layer    │  │    Layer        │                   │
│  │(endpoints)│  │ (business) │  │  (data access)  │                   │
│  └──────────┘  └────────────┘  └────┬───────────┘                   │
│         │                            │    │                          │
│  ┌──────┴──────────┐     ┌──────────┴────────┐                      │
│  │  Redis Client   │     │  asyncpg (outbox)  │                      │
│  │  (redis-py)     │     │  + Kafka Producer  │                      │
│  └──────┬──────────┘     └──────────┬────────┘                      │
└─────────┼───────────────────────────┼───────────────────────────────┘
          │                           │
          ▼                           ▼
┌──────────────────┐      ┌──────────────────────────┐
│  redis:7-alpine   │      │  postgres:16-alpine      │
│  Cache + Rate     │      │  Outbox Table (events)   │
│  Limiter          │      │                          │
└──────────────────┘      └──────────┬───────────────┘
                                     │
                                     │ CDC / Polling
                                     ▼
                          ┌──────────────────────┐
                          │   Kafka (event bus)   │
                          └──────────┬───────────┘
                                     │ consume
                                     ▼
                          ┌──────────────────────┐
                          │  Ingest Consumer      │
                          │  (separate process)   │
                          │  ES index + cache     │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  elasticsearch:8.x    │
                          │  Document Store +     │
                          │  Search Index         │
                          └──────────────────────┘
```

Six containers via Docker Compose:
- **app** — FastAPI application (REST API, outbox writer, Kafka producer)
- **consumer** — Background worker (Kafka consumer → ES index → Redis cache)
- **postgres** — `postgres:16-alpine` (outbox table, event journal)
- **redis** — `redis:7-alpine` (cache + rate limiter)
- **kafka** — Apache Kafka (event stream)
- **elasticsearch** — `elasticsearch:8.x` (document store + search index)

---

## 2. Component Breakdown

### Router Layer
- **`routers/documents.py`** — `POST /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`
- **`routers/search.py`** — `GET /search`
- **`routers/health.py`** — `GET /health`
- Request validation via Pydantic schemas
- Extracts `X-Tenant-ID` header via FastAPI dependency

### Service Layer
- **`services/document_service.py`** — Document CRUD orchestration, outbox writes, cache invalidation
- **`services/search_service.py`** — Query construction, cache-aside logic against ES
- **`services/health_service.py`** — Dependency health aggregation
- Multi-tenancy enforced here — `tenant_id` passed down from router

### Repository Layer
- **`repositories/outbox_repository.py`** — PostgreSQL outbox INSERT/UPDATE
- **`repositories/document_repository.py`** — Elasticsearch queries
- **`repositories/cache_repository.py`** — Redis operations via redis-py async

### Consumer (Separate Process)
- **`consumer/__init__.py`**
- **`consumer/main.py`** — Kafka consumer loop, reads from `documents.ingest` topic
- **`consumer/indexer.py`** — Indexes documents into Elasticsearch and updates Redis cache

---

## 3. Data Flows

### Ingestion Flow (`POST /documents`)
```
Client → Router (validate + tenant_id) → Service (business logic)
       → Outbox Repository (INSERT into PG outbox table)
       → Kafka Producer (publish event to `documents.ingest` topic)
       → Response 202 { id, event_id, status: "pending" }
```

```
Consumer (separate process):
  Kafka consumer (poll `documents.ingest`)
       → parse event (tenant_id, doc_id, title, content, metadata)
       → index into Elasticsearch
       → update outbox status to "completed" (or "failed")
       → (optional) warm Redis cache
```

### Search Flow (`GET /search`)
```
Client → Router (validate + tenant_id) → Service
       → Cache Repository (check redis for cached results)
       → if HIT → return cached results
       → if MISS → Document Repository (ES search query)
                 → rank results → store in cache → return
```

### Document Retrieval Flow (`GET /documents/{id}`)
```
Client → Router → Service
       → Cache Repository (check doc:{tenant}:{id})
       → if HIT → return cached document
       → if MISS → Document Repository (ES get by id + tenant_id)
                 → cache result → return
```

### Deletion Flow (`DELETE /documents/{id}`)
```
Client → Router → Service
       → Document Repository (ES delete by id + tenant_id)
       → Cache Repository (evict doc:{tenant}:{id})
       → Cache Repository (invalidate search cache for tenant)
       → Response 200 { status: "deleted" }
```

### Health Check Flow (`GET /health`)
```
Client → Router → Health Service
       → Ping PostgreSQL (SELECT 1)
       → Ping Redis (PING)
       → Ping Elasticsearch (cluster health)
       → Ping Kafka (metadata request)
       → Aggregate → Response 200 or 503
```

---

## 4. Outbox Schema (PostgreSQL)

```sql
CREATE TABLE document_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    doc_id      UUID,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    event_type  TEXT NOT NULL,  -- 'create', 'update', 'delete'
    status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'completed', 'failed'
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_status ON document_events (status, created_at);
CREATE INDEX idx_outbox_tenant ON document_events (tenant_id, event_id);
```

---

## 5. Elasticsearch Search Design

### Index Mapping
```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "doc_id":       { "type": "keyword" },
      "tenant_id":    { "type": "keyword" },
      "title":        { "type": "text", "analyzer": "english" },
      "content":      { "type": "text", "analyzer": "english" },
      "metadata":     { "type": "object", "enabled": false },
      "created_at":   { "type": "date" },
      "updated_at":   { "type": "date" }
    }
  }
}
```

### Query Pattern
```json
{
  "query": {
    "bool": {
      "must": [
        { "term": { "tenant_id": "tenant_123" } },
        { "multi_match": {
            "query": "user search terms",
            "fields": ["title^2", "content"],
            "type": "best_fields"
          }
        }
      ]
    }
  },
  "from": 0,
  "size": 20
}
```

Title boosted 2x for relevance.

---

## 6. Kafka Event Schema

### Topic: `documents.ingest`

Key: `{tenant_id}` (partitioned by tenant for ordered processing)

Value (JSON):
```json
{
  "event_id": "uuid",
  "event_type": "create | update | delete",
  "tenant_id": "tenant_123",
  "doc_id": "uuid",
  "title": "string",
  "content": "text",
  "metadata": {},
  "timestamp": "ISO8601"
}
```

Retention: 7 days (configurable).

---

## 7. Redis Data Model

| Key Pattern | Type | Purpose | TTL |
|---|---|---|---|
| `doc:{tenant_id}:{doc_id}` | String (JSON) | Document detail cache | configurable (default 300s) |
| `search:{tenant_id}:{hash(query,page,size)}` | String (JSON) | Search result cache | configurable (default 60s) |
| `ratelimit:{tenant_id}:search` | Sorted Set | Sliding window rate limiter | auto |
| `ratelimit:{tenant_id}:index` | Sorted Set | Sliding window rate limiter | auto |
| `ratelimit:global` | Sorted Set | Global rate limit | auto |

Cache TTLs are configurable via `Settings.cache_ttl_doc` and `Settings.cache_ttl_search`.

---

## 8. Multi-Tenancy Strategy

- **Header-based isolation**: `X-Tenant-ID` required on all document/search endpoints.
- Extracted via FastAPI dependency (`Depends`) and injected into every service call.
- All queries include `tenant_id` filter — no cross-tenant data leakage.
- Elasticsearch: tenant-scoped via `term` filter on `tenant_id` keyword field.
- Kafka: topic partitioned by `tenant_id` key for ordered per-tenant processing.
- Cache keys are namespaced per tenant (`doc:{tenant}:{id}`).
- Rate limits tracked and enforced independently per tenant.

---

## 9. Rate Limiting Algorithm

Sliding window counter using Redis sorted sets:

1. On each request, add member `{current_timestamp_ns}` with score `current_timestamp_ms`
2. Remove entries outside the window: `ZREMRANGEBYSCORE -inf (now - window_ms)`
3. Count entries: `ZCARD key`
4. If count > limit → return `429 Too Many Requests`

Limits (configurable via `Settings`):
- **Search**: 100 req/s per tenant
- **Index**: 10 req/s per tenant
- **Global**: 1000 req/s

---

## 10. Caching Strategy & Trade-offs

| Aspect | Strategy | Trade-off |
|---|---|---|
| Document cache | Cache-aside, write-through on invalidate | Stale reads within TTL |
| Search cache | Cache-aside with short TTL | Stale results up to TTL |
| Cache invalidation | On DELETE / POST (clears search cache per tenant) | Invalidation on every write |

---

## 11. Consistency & Trade-off Analysis

| Concern | Choice | Rationale | Trade-off |
|---|---|---|---|
| Write consistency | Eventual (async via outbox + Kafka) | Decouples ingest from search indexing | Lag between write and searchable |
| Search freshness | Near-real-time (seconds) | Kafka → Consumer → ES latency | Not synchronous |
| Cache consistency | Best-effort with TTL | Avoids distributed locking | Stale reads possible within TTL |
| Rate limiter | Sliding window | More accurate than fixed window | Slightly higher memory per key |
| Document of record | Elasticsearch `_source` | Scales horizontally, no blob in RDBMS | ES cluster management needed |
| Outbox reliability | At-least-once delivery | Retries on consumer failure | Idempotency needed in consumer |

---

## 12. Project Structure

```
docex/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan, middleware
│   ├── config.py                # Settings via pydantic-settings
│   ├── dependencies.py          # FastAPI dependency injection (tenant_id, rate limit)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── documents.py         # POST/GET/DELETE /documents
│   │   ├── search.py            # GET /search
│   │   └── health.py            # GET /health
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── documents.py         # Document request/response models
│   │   ├── search.py            # Search request/response models
│   │   ├── health.py            # Health response models
│   │   └── events.py            # Kafka event models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   └── health_service.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── document_repository.py  # Elasticsearch queries
│   │   ├── cache_repository.py     # Redis operations
│   │   └── outbox_repository.py    # PG outbox operations
│   ├── kafka/
│   │   ├── __init__.py
│   │   └── producer.py          # Kafka async producer
│   └── middleware/
│       ├── __init__.py
│       └── rate_limiter.py
├── consumer/
│   ├── __init__.py
│   ├── main.py                  # Kafka consumer loop
│   └── indexer.py               # ES indexing + cache warm
├── scripts/
│   ├── seed.py                  # Seed ES from jsonl
│   └── init_es.py               # Create ES index with mapping
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.consumer
├── pyproject.toml
├── requirements.txt
├── SPEC.md
├── DESIGN.md
├── REQUIREMENTS.md
├── PROGRESS.md
└── README.md
```

---

## 13. Low-Level Design (Implementation Plan)

### Implementation Order (6 phases)

### Phase 1 — Foundation (config + dependencies)

**`app/config.py`** — `Settings(BaseSettings)` with:

| Field | Default | Description |
|---|---|---|
| `database_url` | `postgresql://docsextract:docsextract@localhost:5432/docex` | PG outbox connection |
| `redis_url` | `redis://localhost:6379/0` | Redis connection |
| `elasticsearch_url` | `http://localhost:9200` | ES connection |
| `kafka_bootstrap_servers` | `localhost:9092` | Kafka broker |
| `kafka_topic` | `documents.ingest` | Ingest topic name |
| `kafka_group_id` | `documents-ingest-consumer` | Consumer group |
| `rate_limit_search` | 100 | req/s per tenant |
| `rate_limit_index` | 10 | req/s per tenant |
| `rate_limit_global` | 1000 | req/s global |
| `cache_ttl_doc` | 300 | seconds |
| `cache_ttl_search` | 60 | seconds |
| `es_index_name` | `documents` | ES index name |
| `version` | `0.1.0` | — |

**`app/main.py`** — FastAPI app factory:
- Lifespan: create asyncpg pool + redis client + ES client + Kafka producer on start, close on shutdown
- Store connections in `app.state`
- Register routers under prefixes
- Exception handlers for 400/404/429/500 → `{"error": {"code", "message", "detail"}}`

**`app/dependencies.py`** — FastAPI `Depends` callables:
- `get_tenant_id()` — extracts `X-Tenant-ID` header, 400 if missing
- `get_db_pool()` — returns `request.app.state.db_pool`
- `get_redis()` — returns `request.app.state.redis`
- `get_elasticsearch()` — returns `request.app.state.es`
- `get_kafka_producer()` — returns `request.app.state.kafka_producer`
- `rate_limit(group: str, max_rps: int)` — factory returning a `Depends`-compatible callable

### Phase 2 — Schemas

| File | Models |
|---|---|
| `schemas/common.py` | `ErrorResponse(code, message, detail)` |
| `schemas/documents.py` | `DocumentCreate(title, content, metadata?)`, `DocumentResponse(id, title, content, metadata, created_at, updated_at)`, `IngestResponse(id, event_id, status)` |
| `schemas/search.py` | `SearchResult(id, title, content?, rank?)`, `SearchResponse(results, total, page, size)` |
| `schemas/health.py` | `DependencyStatus(status, latency_ms)`, `HealthResponse(status, version, dependencies)` |
| `schemas/events.py` | `DocumentEvent(event_id, event_type, tenant_id, doc_id, title, content, metadata, timestamp)` |

### Phase 3 — Data Access

**`repositories/outbox_repository.py`** — PostgreSQL outbox via asyncpg:
- `insert_event(conn, tenant_id, title, content, metadata, doc_id, event_type) → dict`
- `update_status(conn, event_id, status, error?) → None`
- `get_pending_events(conn, limit) → list[dict]`

**`repositories/document_repository.py`** — Elasticsearch:
- `index_document(es, tenant_id, doc_id, title, content, metadata) → dict`
- `get_by_id(es, tenant_id, doc_id) → dict | None`
- `delete(es, tenant_id, doc_id) → bool`
- `search(es, tenant_id, query, from_, size) → (list[dict], total)`
- `ping(es) → bool`

**`repositories/cache_repository.py`** — Redis:
- `get/set/delete_document(tenant_id, doc_id)` — doc detail cache
- `get/set_search_results(tenant_id, query_hash, page, size)` — search cache
- `invalidate_search_cache(tenant_id)` — scan & delete `search:{tenant_id}:*`
- `check_rate_limit(key, max_requests, window_ms) → bool` — sliding window counter
- `ping() → bool`

### Phase 4 — Kafka Producer

**`app/kafka/producer.py`**:
- Async Kafka producer (aiokafka)
- `publish_event(kafka_producer, topic, event: DocumentEvent) → None`
- Serializes event to JSON, sends with `tenant_id` as key

### Phase 5 — Business Logic & API

**`services/document_service.py`**:
- `create(tenant_id, title, content, metadata)` → insert outbox → publish Kafka event → return `{id, event_id, status: "pending"}`
- `get(tenant_id, doc_id)` → cache-aside: Redis → ES → Redis → return
- `delete(tenant_id, doc_id)` → ES delete → evict doc cache → invalidate search cache

**`services/search_service.py`**:
- `search(tenant_id, query, page, size)` → cache-aside: Redis → ES → Redis → return

**`services/health_service.py`**:
- `check()` → ping PG + Redis + ES + Kafka → aggregate → 200 or 503

**`routers/documents.py`** — prefix `/documents`:
| Route | Depends | Returns |
|---|---|---|
| `POST /` | `get_tenant_id`, `rate_limit("index", 10)` | 202 IngestResponse |
| `GET /{id}` | `get_tenant_id` | 200 DocumentResponse / 404 |
| `DELETE /{id}` | `get_tenant_id`, `rate_limit("index", 10)` | 200 / 404 |

**`routers/search.py`** — prefix `/search`:
| Route | Depends | Returns |
|---|---|---|
| `GET /` | `get_tenant_id`, `rate_limit("search", 100)` | 200 SearchResponse |
| Query: `q` (required), `page` (default 1), `size` (default 20, max 100) | | |

**`routers/health.py`** — prefix `/health`:
| Route | Depends | Returns |
|---|---|---|
| `GET /` | none | 200 HealthResponse / 503 |

### Phase 6 — Consumer

**`consumer/main.py`**:
- `main()` — Kafka consumer loop
  - Poll `documents.ingest` topic
  - For each message: deserialize → call indexer → update outbox status
  - Handle retries, dead-letter on repeated failures
  - Graceful shutdown on SIGTERM

**`consumer/indexer.py`**:
- `index_document(es, event) → bool` — indexes into ES
- `update_cache(redis, event) → None` — warms Redis cache
- `update_outbox_status(pool, event_id, status, error?) → None`

### Dependency Graph

```
Router
  → Depends(rate_limit(group, rps))
      → Depends(get_redis) + Depends(get_tenant_id)
  → Service(Repo, Cache)
      → Depends(get_db_pool) + Depends(get_redis) + Depends(get_elasticsearch)

Consumer
  → Kafka Consumer (aiokafka)
  → Elasticsearch Client
  → Redis Client
  → asyncpg Pool (for outbox status updates)
```

### Key Design Decisions

| Decision | Rationale |
|---|---|---|
| Dual-write: outbox INSERT + Kafka publish | Reliable async ingestion with PG journal for debugging |
| ES as document store | Horizontally scalable, no blob in RDBMS, native full-text search |
| Consumer idempotency via ES upsert | ES `index` is naturally idempotent by `doc_id`; no explicit event_id tracking needed |
| Approximate search total (ES default) | Fast; `track_total_hits` not set |
| Dead letter: log + mark failed in outbox | Simpler than DLQ topic; visible in PG for replay |
| Partitioned by tenant_id (Kafka) | Ordered per-tenant event processing |
| Polling-based outbox (not Debezium) | Simpler for MVP, no extra infrastructure |
| Separate consumer process | Independent scaling, doesn't block API |
| Cache-aside pattern | Simple, no write amplification |
| Sliding window rate limit | More accurate than fixed window |
