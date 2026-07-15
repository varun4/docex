# DocEx — Specification

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Search Engine**: Elasticsearch 8.x
- **Event Bus**: Apache Kafka
- **Cache & Rate Limiting**: Redis (via Docker)
- **Outbox Store**: PostgreSQL 16 (event journal only)
- **Orchestration**: Docker Compose (app + consumer + postgres + redis + kafka + elasticsearch)

---

## Architecture

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────────┐
│ FastAPI   │───▶│ Postgres │───▶│  Kafka    │───▶│  Consumer    │
│ (:8000)   │    │ (outbox) │    │ (event bus)│    │  (worker)    │
└─────┬────┘    └──────────┘    └───────────┘    └──────┬───────┘
      │                                                  │
      ▼                                                  ▼
┌──────────┐                                    ┌──────────────┐
│  Redis   │                                    │ Elasticsearch │
│ (cache)  │                                    │ (:9200)      │
└──────────┘                                    │ (store+search)│
                                                 └──────────────┘
```

---

## API Contracts

| Method | Endpoint | Auth Header | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| POST | `/api/v1/documents` | `X-Tenant-ID` | `{title, content, metadata?}` | `202 {id, event_id, status: "pending"}` |
| GET | `/api/v1/search?q={query}&page=1&size=20` | `X-Tenant-ID` | — | `{results[], total, page, size}` |
| GET | `/api/v1/documents/{id}` | `X-Tenant-ID` | — | `{id, title, content, metadata, created_at, updated_at}` |
| DELETE | `/api/v1/documents/{id}` | `X-Tenant-ID` | — | `{status}` |
| GET | `/health` | — | — | `{status, version, dependencies}` |

### Document Schema (Request/Response)
```json
{
  "id": "uuid (response only)",
  "title": "string (required)",
  "content": "text (required)",
  "metadata": "object (optional, arbitrary JSON)"
}
```

### Ingest Response
```json
{
  "id": "uuid",
  "event_id": "uuid",
  "status": "pending"
}
```

---

## Outbox Schema (PostgreSQL)

```sql
CREATE TABLE document_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    doc_id      UUID,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    event_type  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
```

---

## Elasticsearch Index Mapping

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
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

---

## Kafka Topics

| Topic | Partitions | Key | Retention |
|---|---|---|---|
| `documents.ingest` | 3 | `tenant_id` | 7 days |

### Event Schema
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

---

## Multi-Tenancy

- **Header-based**: `X-Tenant-ID` header required on every authenticated request.
- ES: tenant-scoped via `term` filter on `tenant_id` keyword.
- Kafka: partitioned by `tenant_id` key for ordered per-tenant processing.
- Cache: namespaced per tenant (`doc:{tenant}:{id}`).

---

## Caching Strategy

| Cache | Key Pattern | TTL | Invalidation |
|-------|------------|-----|-------------|
| Document detail | `doc:{tenant}:{id}` | configurable (default 5 min) | On UPDATE / DELETE |
| Search results | `search:{tenant}:{hash(query,page,size)}` | configurable (default 1 min) | On new document index |

---

## Rate Limiting

- **Search**: 100 requests/second per tenant (configurable)
- **Indexing**: 10 requests/second per tenant (configurable)
- **Global**: 1000 requests/second (across all tenants)
- Algorithm: Sliding window via Redis sorted sets

---

## Consistency Model

- **Write consistency**: Eventual (async via outbox + Kafka → ES)
- **Search freshness**: Near-real-time (seconds of lag)
- **Cache consistency**: Best-effort with configurable TTL
- **Outbox reliability**: At-least-once delivery (idempotent consumer)

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

HTTP status codes used: `200`, `202`, `400`, `404`, `429`, `500`, `503`.

---

## Health Check

`GET /health` returns:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "dependencies": {
    "postgres": { "status": "up", "latency_ms": 2 },
    "redis": { "status": "up", "latency_ms": 1 },
    "elasticsearch": { "status": "up", "latency_ms": 3 },
    "kafka": { "status": "up", "latency_ms": 5 }
  }
}
```

Response status:
- `"healthy"` + `200` — all dependencies up
- `"degraded"` + `503` — at least one dependency up, others down
- `"unavailable"` + `503` — all dependencies down
