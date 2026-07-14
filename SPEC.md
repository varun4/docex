# DocExtract — Specification

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Search Engine**: PostgreSQL Full-Text Search (tsvector + GIN index)
- **Cache & Rate Limiting**: Redis (via Docker)
- **Orchestration**: Docker Compose (app + postgres + redis)

---

## Architecture (Prototype)

Single FastAPI service handling REST API with three backing services:

```
┌─────────────┐     ┌──────────┐     ┌──────────┐
│  FastAPI App │────▶│ Postgres │────▶│  Redis   │
│  (:8000)     │     │ (:5432)  │     │ (:6379)  │
└─────────────┘     └──────────┘     └──────────┘
       │                                  │
       │  Health checks                   │
       ▼                                  ▼
   /health                            Cache + Rate
   endpoint                           Limiter + Queue
```

---

## API Contracts

| Method | Endpoint | Auth Header | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| POST | `/documents` | `X-Tenant-ID` | `{id?, title, content, metadata?}` | `{id, status}` |
| GET | `/search?q={query}&page=1&size=20` | `X-Tenant-ID` | — | `{results[], total, page, size}` |
| GET | `/documents/{id}` | `X-Tenant-ID` | — | `{id, title, content, metadata, created_at, updated_at}` |
| DELETE | `/documents/{id}` | `X-Tenant-ID` | — | `{status}` |
| GET | `/health` | — | — | `{status, dependencies: {postgres, redis}}` |

### Document Schema (Request/Response)
```json
{
  "id": "uuid (auto-generated if omitted)",
  "title": "string (required)",
  "content": "text (required)",
  "metadata": "object (optional, arbitrary JSON)"
}
```

---

## Database Schema

```sql
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_search
    ON documents
    USING GIN (search_vector);

CREATE INDEX idx_documents_tenant
    ON documents (tenant_id, id);
```

---

## Multi-Tenancy

- **Header-based**: `X-Tenant-ID` header required on every authenticated request.
- All queries include `WHERE tenant_id = :tenant_id` to enforce isolation.
- No cross-tenant data leakage.

---

## Caching Strategy

| Cache | Key Pattern | TTL | Invalidation |
|-------|------------|-----|-------------|
| Document detail | `doc:{tenant}:{id}` | 5 min | On UPDATE / DELETE |
| Search results | `search:{tenant}:{query_hash}:{page}:{size}` | 1 min | On new document index |
| Rate limiter | `ratelimit:{tenant}:{endpoint_group}` | Sliding window | Automatic (1s windows) |

---

## Rate Limiting

- **Search**: 100 requests/second per tenant (configurable)
- **Indexing**: 10 requests/second per tenant (configurable)
- **Global**: 1000 requests/second (across all tenants)
- Algorithm: Sliding window via Redis sorted sets

---

## Async Indexing

- `POST /documents` can be synchronous (direct DB write) or asynchronous (via Redis queue).
- Async path: job enqueued → immediate `202 {status: "pending"}` response → background worker consumes queue → writes to PostgreSQL → updates cache.
- Default: synchronous for simplicity; async configurable.

---

## Consistency Model

- **Strong consistency** for direct CRUD (`GET`/`DELETE`/sync `POST`).
- **Eventual consistency** for async indexing path (queue-based).
- Search index is **near-real-time**: PostgreSQL FTS is updated on commit.

---

## Error Handling

All errors return a standardized JSON envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Document not found",
    "detail": "No document with id xyz exists for this tenant"
  }
}
```

HTTP status codes used: `200`, `201`, `202`, `400`, `401`, `404`, `429`, `500`, `503`.

---

## Health Check

`GET /health` returns:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "dependencies": {
    "postgres": { "status": "up", "latency_ms": 2 },
    "redis": { "status": "up", "latency_ms": 1 }
  }
}
```

Returns `503` if any critical dependency is down.
