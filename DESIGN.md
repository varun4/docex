# DocEx — High-Level Design

## 1. System Architecture

```
┌─────────────────────────────────────┐
│         Client / API Consumer        │
└────────────┬────────────────────────┘
             │ HTTP (REST)
             ▼
┌──────────────────────────────────────────────────┐
│              FastAPI Service (:8000)              │
│  ┌──────────┐  ┌────────────┐  ┌──────────────┐  │
│  │  Router   │→ │  Service   │→ │  Repository   │  │
│  │   Layer   │  │   Layer    │  │    Layer      │  │
│  │(endpoints)│  │ (business) │  │   (data)     │  │
│  └──────────┘  └────────────┘  └──────┬───────┘  │
│         │                             │          │
│  ┌──────────────────────┐   ┌────────┴────────┐  │
│  │   Redis Client (aioredis) │   asyncpg      │  │
│  └──────────┬───────────┘   └────────┬────────┘  │
└─────────────┼────────────────────────┼───────────┘
              │                        │
              ▼                        ▼
    ┌─────────────────┐     ┌────────────────────┐
    │   redis:7-alpine │     │  postgres:16-alpine│
    │    Cache +       │     │    FTS Engine      │
    │    Rate Limiter  │     │    + Storage       │
    │    Async Queue   │     │                    │
    └─────────────────┘     └────────────────────┘
```

Three containers via Docker Compose:
- **app** — FastAPI application (custom Dockerfile)
- **redis** — `redis:7-alpine` (official image, no custom Dockerfile)
- **postgres** — `postgres:16-alpine` (official image, no custom Dockerfile)

---

## 2. Component Breakdown

### Router Layer
- **`routers/documents.py`** — `POST /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`
- **`routers/search.py`** — `GET /search`
- **`routers/health.py`** — `GET /health`
- Request validation via Pydantic schemas
- Extracts `X-Tenant-ID` header via FastAPI dependency

### Service Layer
- **`services/document_service.py`** — Document CRUD orchestration, cache invalidation
- **`services/search_service.py`** — Query construction, cache-aside logic, result ranking
- **`services/health_service.py`** — Dependency health aggregation
- Multi-tenancy enforced here — `tenant_id` passed down from router

### Repository Layer
- **`repositories/document_repository.py`** — PostgreSQL queries via asyncpg
- **`repositories/cache_repository.py`** — Redis operations via redis-py async
- All SQL/Redis commands isolated here; services never touch DB/Redis directly

---

## 3. Data Flows

### Indexing Flow (`POST /documents`)
```
Client → Router (validate + tenant_id) → Service (business logic) 
       → Repository (INSERT into PostgreSQL) 
       → Cache Repository (invalidate search cache for tenant)
       → Response 201 { id, status: "indexed" }
```

### Search Flow (`GET /search`)
```
Client → Router (validate + tenant_id) → Service 
       → Cache Repository (check redis for cached results)
       → if HIT → return cached results
       → if MISS → Document Repository (tsquery on PostgreSQL)
                 → rank results → store in cache → return
```

### Document Retrieval Flow (`GET /documents/{id}`)
```
Client → Router → Service 
       → Cache Repository (check doc:{tenant}:{id})
       → if HIT → return cached document
       → if MISS → Document Repository (SELECT by id + tenant_id)
                 → cache result → return
```

### Deletion Flow (`DELETE /documents/{id}`)
```
Client → Router → Service 
       → Document Repository (DELETE where id + tenant_id)
       → Cache Repository (evict doc:{tenant}:{id})
       → Cache Repository (invalidate search cache for tenant)
       → Response 200 { status: "deleted" }
```

### Health Check Flow (`GET /health`)
```
Client → Router → Health Service 
       → Ping PostgreSQL (SELECT 1)
       → Ping Redis (PING)
       → Aggregate → Response 200 or 503
```

---

## 4. PostgreSQL Full-Text Search Design

### Generated tsvector Column
```sql
search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
) STORED;
```

### Query Pattern
```sql
SELECT id, title, content, metadata,
       ts_rank(search_vector, plainto_tsquery('english', $2), 1) AS rank
FROM documents
WHERE tenant_id = $1
  AND search_vector @@ plainto_tsquery('english', $2)
ORDER BY rank DESC
LIMIT $3 OFFSET $4;
```

### Index Strategy
- **GIN index** on `search_vector` — supports full-text searches
- **B-tree index** on `(tenant_id, id)` — supports tenant-scoped lookups and filtered searches
- `plainto_tsquery` normalizes user input (strips punctuation, handles stemming)

---

## 5. Redis Data Model

| Key Pattern | Type | Purpose | TTL |
|---|---|---|---|
| `doc:{tenant_id}:{doc_id}` | String (JSON) | Document detail cache | 300s |
| `search:{tenant_id}:{hash(query,page,size)}` | String (JSON) | Search result cache | 60s |
| `ratelimit:{tenant_id}:search` | Sorted Set | Sliding window rate limiter | auto |
| `ratelimit:{tenant_id}:index` | Sorted Set | Sliding window rate limiter | auto |
| `ratelimit:global` | Sorted Set | Global rate limit | auto |

---

## 6. Multi-Tenancy Strategy

- **Header-based isolation**: `X-Tenant-ID` is required on all document/search endpoints.
- Extracted via FastAPI dependency (`Depends`) and injected into every service call.
- All SQL queries include `WHERE tenant_id = :tenant_id` — no tenant_id predicate = no results.
- Cache keys are namespaced per tenant (`doc:{tenant}:{id}`).
- Rate limits tracked and enforced independently per tenant.

---

## 7. Rate Limiting Algorithm

Sliding window counter using Redis sorted sets:

1. On each request, add member `{current_timestamp_ns}` with score `current_timestamp_ms`
2. Remove entries outside the window: `ZREMRANGEBYSCORE -inf (now - window_ms)`
3. Count entries: `ZCARD key`
4. If count > limit → return `429 Too Many Requests`

Limits (configurable):
- **Search**: 100 req/s per tenant
- **Index**: 10 req/s per tenant
- **Global**: 1000 req/s

---

## 8. Caching Strategy & Trade-offs

| Aspect | Strategy | Trade-off |
|---|---|---|
| Document cache | Cache-aside, write-through on invalidate | Stale reads within TTL (300s) |
| Search cache | Cache-aside with short TTL | Stale results up to 60s |
| Cache invalidation | On DELETE and POST (new index clears search cache per tenant) | Invalidation on every write |

---

## 9. Consistency & Trade-off Analysis

| Concern | Choice | Rationale | Trade-off |
|---|---|---|---|
| Search freshness | Near-real-time (commit-time) | Simpler than async indexing pipeline | Slightly higher write latency |
| Cache consistency | Best-effort with TTL | Avoids distributed locking complexity | Stale reads possible within TTL |
| Rate limiter | Sliding window | More accurate than fixed window | Slightly higher memory per key |
| Write semantics | Synchronous | Strong consistency for CRUD | Lower write throughput |

---

## 10. Project Structure

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
│   │   └── health.py            # Health response models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   └── health_service.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── document_repository.py  # PostgreSQL queries
│   │   └── cache_repository.py     # Redis operations
│   └── middleware/
│       ├── __init__.py
│       └── rate_limiter.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── SPEC.md
├── DESIGN.md
├── REQUIREMENTS.md
├── PROGRESS.md
└── README.md

---

## 11. Low-Level Design (Implementation Plan)

### Implementation Order (16 files, 4 phases)

#### Phase 1 — Foundation

**`app/config.py`** — `Settings(BaseSettings)` with:
| Field | Default |
|---|---|
| `database_url` | `postgresql://docsextract:docsextract@localhost:5432/docex` |
| `redis_url` | `redis://localhost:6379/0` |
| `rate_limit_search` | 100 req/s |
| `rate_limit_index` | 10 req/s |
| `rate_limit_global` | 1000 req/s |
| `cache_ttl_doc` | 300s |
| `cache_ttl_search` | 60s |
| `version` | `0.1.0` |

**`app/main.py`** — FastAPI app factory:
- Lifespan: create asyncpg pool + redis client on start, close on shutdown
- Store connections in `app.state`
- Register routers under prefixes
- Exception handlers for 400/404/429/500 → `{"error": {"code", "message", "detail"}}`

**`app/dependencies.py`** — FastAPI `Depends` callables:
- `get_tenant_id()` — extracts `X-Tenant-ID` header, 400 if missing
- `get_db_pool()` — returns `request.app.state.db_pool`
- `get_redis()` — returns `request.app.state.redis`
- `rate_limit(group: str, max_rps: int)` — factory returning a `Depends`-compatible callable
  - Sliding window via Redis: `ZADD` → `ZREMRANGEBYSCORE` → `ZCARD` → compare with limit
  - Raises 429 if exceeded

#### Phase 2 — Schemas

| File | Models |
|---|---|
| `schemas/common.py` | `ErrorResponse(code, message, detail)` |
| `schemas/documents.py` | `DocumentCreate(title, content, metadata?)`, `DocumentResponse(id, title, content, metadata, created_at, updated_at)` |
| `schemas/search.py` | `SearchResult(id, title, content?, rank?)`, `SearchResponse(results, total, page, size)` |
| `schemas/health.py` | `DependencyStatus(status, latency_ms)`, `HealthResponse(status, version, dependencies)` |

#### Phase 3 — Data Access

**`repositories/document_repository.py`** — PostgreSQL via asyncpg:
- `create(conn, tenant_id, title, content, metadata) → dict`
- `get_by_id(conn, tenant_id, id) → dict | None`
- `delete(conn, tenant_id, id) → bool`
- `search(conn, tenant_id, query, limit, offset) → (list[dict], total_count)`

**`repositories/cache_repository.py`** — Redis:
- `get/set/delete_document(tenant_id, doc_id)` — doc detail cache
- `get/set_search_results(tenant_id, query_hash, page, size)` — search cache
- `invalidate_search_cache(tenant_id)` — scan & delete `search:{tenant_id}:*`
- `check_rate_limit(key, max_requests, window_ms) → bool` — sliding window counter
- `ping() → bool`

#### Phase 4 — Business Logic & API

**`services/document_service.py`**:
- `create(tenant_id, title, content, metadata)` → PG insert → invalidate search cache → return
- `get(tenant_id, doc_id)` → cache-aside: Redis → PG → Redis → return
- `delete(tenant_id, doc_id)` → PG delete → evict doc cache → invalidate search cache

**`services/search_service.py`**:
- `search(tenant_id, query, page, size)` → cache-aside: Redis → PG FTS → Redis → return

**`services/health_service.py`**:
- `check()` → ping PG (SELECT 1) + Redis (PING) → aggregate → 200 or 503

**`routers/documents.py`** — prefix `/documents`:
| Route | Depends | Returns |
|---|---|---|
| `POST /` | `get_tenant_id`, `rate_limit("index", 10)` | 201 DocumentResponse |
| `GET /{id}` | `get_tenant_id`, `rate_limit("search", 100)` | 200 DocumentResponse / 404 |
| `DELETE /{id}` | `get_tenant_id`, `rate_limit("index", 10)` | 200 / 404 |

**`routers/search.py`** — prefix `/search`:
| Route | Depends | Returns |
|---|---|---|
| `GET /` | `get_tenant_id`, `rate_limit("search", 100)` | 200 SearchResponse |
| Query: `q` (required), `page` (default 1), `size` (default 20, max 100) | | |

**`routers/health.py`** — prefix `/health`:
| Route | Depends | Returns |
|---|---|---|
| `GET /` | none | 200 or 503 |

### Dependency Graph

```
Router
  → Depends(rate_limit(group, rps))
      → Depends(get_redis) + Depends(get_tenant_id)
  → Service(Repo, Cache)
      → Depends(get_db_pool) + Depends(get_redis)
```

All services and repos are stateless — created per-request via lightweight constructors.

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Rate limiter in `dependencies.py` (not middleware) | Per-route granularity, explicit, testable |
| Stateless services/repos | No DI framework needed, simple constructors |
| Cache-aside pattern | Simple, no write amplification |
| Sliding window rate limit | More accurate than fixed window |
| Exception handlers for errors | Clean separation of error formatting |
```
