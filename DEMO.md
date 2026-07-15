# DocEx — Demo

This guide demonstrates all features of DocEx end-to-end. It assumes the service is running via Docker Compose (see `README.md` for setup).

---

## Quick Start

```bash
git clone https://github.com/varun4/docex.git
cd docex
cp .env.example .env

# Start all services
docker compose up -d --build

# Initialize database and Elasticsearch schemas
docker compose run --rm app python scripts/init_db.py
docker compose run --rm app python scripts/init_es.py
```

The API is now available at `http://localhost` (or `http://localhost:8080` if `CADDY_HTTP_PORT` is set to 8080 in `.env`).

---

## 1. Health Check

Verify all dependencies are reachable:

```bash
curl http://localhost/api/v1/health | jq
```

Expected response (all deps `"up"`):

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "dependencies": {
    "postgres":       { "status": "up", "latency_ms": 0.7 },
    "redis":          { "status": "up", "latency_ms": 0.3 },
    "elasticsearch":  { "status": "up", "latency_ms": 5.2 },
    "kafka":          { "status": "up", "latency_ms": 3.0 }
  }
}
```

If any dependency is down, status becomes `"degraded"` and returns HTTP 503.

---

## 2. Async Document Ingest

Documents are ingested asynchronously. The API returns immediately with an `event_id`; a background consumer indexes into Elasticsearch.

```bash
curl -s -X POST http://localhost/api/v1/documents \
  -H "X-Tenant-ID: stardewvalley" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Stardrop",
    "content": "A rare fruit that empowers those who eat it. Grown from a Stardrop seed.",
    "metadata": { "source": "wiki", "type": "fruit" }
  }' | jq
```

Expected response (HTTP 202):

```json
{
  "id": "a1b2c3d4-...",
  "event_id": "e5f6g7h8-...",
  "status": "pending"
}
```

**What happens under the hood (no CPU-bound work in the API path):**

```
POST /api/v1/documents
  ──▶ OutboxRepository: INSERTS event into PostgreSQL document_events table
  ──▶ KafkaProducer: publishes event to documents.ingest topic
  ──▶ Response: 202 { id, event_id, status: "pending" }   ← fast, no hashing
         │
         ▼  (background, < 1s)
      Consumer polls Kafka
         │
         ├──▶ compute hash → check ES for duplicate
         │     ── duplicate? → mark event "duplicate", skip indexing
         │     ── new?       → continue
         ├──▶ indexDocument: ES index with BM25 scoring
         ├──▶ cacheWarm: Redis SETEX doc:{tenant}:{id}
         ├──▶ invalidateSearchCache: Redis SCAN + DEL search:{tenant}:*
         └──▶ updateOutbox: mark event "completed"
```

---

## 3. Event Tracking

After ingesting a document, you can poll the event status to know when processing completes:

```bash
# Ingest returns an event_id
EVENT_ID=$(curl -s -X POST http://localhost/api/v1/documents \
  -H "X-Tenant-ID: stardewvalley" \
  -H "Content-Type: application/json" \
  -d '{"title": "Tracked Doc", "content": "Watch me get indexed"}' | jq -r '.event_id')

echo "Event ID: $EVENT_ID"

# Poll until terminal status
while true; do
  RESP=$(curl -s "http://localhost/api/v1/documents/events/$EVENT_ID" \
    -H "X-Tenant-ID: stardewvalley")
  STATUS=$(echo "$RESP" | jq -r '.status')
  echo "$RESP" | jq
  case "$STATUS" in
    completed|failed|duplicate) break ;;
  esac
  sleep 1
done
```

Expected poll sequences:

**New document** — consumer indexes it:
```json
{ "event_id": "...", "status": "pending",    "error": null }
{ "event_id": "...", "status": "completed",  "error": null }
```

**Duplicate content** — consumer skips indexing:
```json
{ "event_id": "...", "status": "pending",      "error": null }
{ "event_id": "...", "status": "duplicate",    "error": "duplicate of existing document <doc_id>" }
```

If processing fails, `status` is `"failed"` and `error` contains the reason.

## 4. Document Retrieval

Once the consumer has indexed the document (typically < 1 second), retrieve it by ID:

```bash
# Replace with the id from the ingest response
DOC_ID="a1b2c3d4-..."

curl -s http://localhost/api/v1/documents/$DOC_ID \
  -H "X-Tenant-ID: stardewvalley" | jq
```

Expected response (HTTP 200):

```json
{
  "id": "a1b2c3d4-...",
  "title": "Stardrop",
  "content": "A rare fruit that empowers those who eat it. Grown from a Stardrop seed.",
  "metadata": { "source": "wiki", "type": "fruit" },
  "created_at": "2026-07-15T12:00:00Z",
  "updated_at": "2026-07-15T12:00:00Z"
}
```

**Cache-aside flow:**

```
GET /api/v1/documents/{id}
  ──▶ Redis GET doc:{tenant}:{id}
       ├── HIT  ──▶ return cached DocumentResponse
       └── MISS ──▶ Elasticsearch GET by doc_id + tenant_id
                    ──▶ Redis SETEX doc:{tenant}:{id} (TTL 300s)
                    ──▶ return DocumentResponse
```

Try it twice — the second request hits Redis and is faster.

---

## 5. Full-Text Search

Search across all documents for a tenant. Uses Elasticsearch `multi_match` with title boost (2x):

```bash
curl -s "http://localhost/api/v1/search?q=stardrop&page=1&size=10" \
  -H "X-Tenant-ID: stardewvalley" | jq
```

Expected response (HTTP 200):

```json
{
  "results": [
    {
      "id": "a1b2c3d4-...",
      "title": "Stardrop",
      "rank": 58.01
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

**Search features:**
- **BM25 relevance scoring** — Elasticsearch's default ranking algorithm
- **Title boost (2x)** — matches in `title` field rank higher than `content`
- **Pagination** — `page` (default 1) and `size` (default 20, max 100)
- **Cache-aside** — results cached in Redis for 60s; subsequent identical queries skip ES
- **Multi-tenant isolation** — `term` filter on `tenant_id` ensures no cross-tenant leakage

Try partial or fuzzy queries — ES handles stemming, typos, and ranking:

```bash
curl -s "http://localhost/api/v1/search?q=fr&page=1&size=5" \
  -H "X-Tenant-ID: stardewvalley" | jq '.results[].title'
```

---

## 6. Document Deletion

Delete a document from Elasticsearch and evict its cache entries:

```bash
curl -s -X DELETE "http://localhost/api/v1/documents/$DOC_ID" \
  -H "X-Tenant-ID: stardewvalley" | jq
```

Expected response (HTTP 200):

```json
{
  "status": "deleted"
}
```

**What happens:**

```
DELETE /api/v1/documents/{id}
  ──▶ Elasticsearch: DELETE by doc_id + tenant_id
  ──▶ Redis: DEL doc:{tenant}:{id}
  ──▶ Redis: SCAN + DEL search:{tenant}:* (invalidate all search caches for tenant)
  ──▶ Response: 200 { status: "deleted" }
```

Verify deletion:

```bash
curl -s "http://localhost/api/v1/documents/$DOC_ID" \
  -H "X-Tenant-ID: stardewvalley" | jq
# Returns 404 NOT_FOUND
```

---

## 7. Multi-Tenancy

DocEx isolates data by tenant using the `X-Tenant-ID` header. Demonstrate with two tenants:

```bash
# Ingest into tenant-a
curl -s -X POST http://localhost/api/v1/documents \
  -H "X-Tenant-ID: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"title": "Alpha Doc", "content": "This belongs to tenant A"}' | jq

# Ingest into tenant-b
curl -s -X POST http://localhost/api/v1/documents \
  -H "X-Tenant-ID: tenant-b" \
  -H "Content-Type: application/json" \
  -d '{"title": "Beta Doc", "content": "This belongs to tenant B"}' | jq

sleep 3  # Wait for consumer

# Search tenant-a — only Alpha Doc appears
curl -s "http://localhost/api/v1/search?q=doc&size=10" \
  -H "X-Tenant-ID: tenant-a" | jq '.results[].title'
# → "Alpha Doc"

# Search tenant-b — only Beta Doc appears
curl -s "http://localhost/api/v1/search?q=doc&size=10" \
  -H "X-Tenant-ID: tenant-b" | jq '.results[].title'
# → "Beta Doc"
```

**Isolation mechanisms:**

| Layer | Isolation |
|-------|-----------|
| Elasticsearch | `term` filter on `tenant_id` keyword field in every query |
| Kafka | Topic partitioned by `tenant_id` key — ordered per-tenant processing |
| Redis cache | Keys namespaced as `doc:{tenant}:{id}` and `search:{tenant}:{hash}` |
| Rate limiting | Separate counters per tenant: `ratelimit:{tenant}:{group}` |

---

## 8. Rate Limiting

Rate limits are enforced via a sliding window counter in Redis. Defaults:
- **Search**: 100 req/s per tenant
- **Index**: 50 req/s per tenant
- **Global**: 500 req/s (across all tenants)

Hit the rate limit to see the 429 response:

```bash
# Rapid-fire requests to trigger rate limit
for i in $(seq 1 110); do
  curl -s -o /dev/null -w "%{http_code} " \
    "http://localhost/api/v1/search?q=test" \
    -H "X-Tenant-ID: ratelimit-test"
done
echo ""
```

The first ~100 requests return `200`, subsequent ones return `429`:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests",
    "detail": "Rate limit of 100 req/s exceeded for search"
  }
}
```

Rate limit headers are returned on every response:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
```

---

## 9. Error Handling

All errors use a standardized JSON envelope with `ErrorCode` enum values.

**Missing tenant (400):**

```bash
curl -s "http://localhost/api/v1/search?q=test" | jq
```

```json
{
  "error": {
    "code": "MISSING_TENANT",
    "message": "Missing tenant",
    "detail": "X-Tenant-ID header is required"
  }
}
```

**Not found (404):**

```bash
curl -s "http://localhost/api/v1/documents/00000000-0000-0000-0000-000000000000" \
  -H "X-Tenant-ID: stardewvalley" | jq
```

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Document not found",
    "detail": "No document with id 00000000-0000-0000-0000-000000000000"
  }
}
```

**Validation error (400):**

```bash
curl -s -X POST http://localhost/api/v1/documents \
  -H "X-Tenant-ID: stardewvalley" \
  -H "Content-Type: application/json" \
  -d '{"title": ""}' | jq
```

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation error",
    "detail": [...]
  }
}
```

---

## 10. Prometheus Metrics

DocEx exposes Prometheus metrics at `/api/v1/metrics`:

```bash
curl -s http://localhost/api/v1/metrics | grep -E "docex_|docsextract_" | head -20
```

Available metrics:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `docex_requests_total` | Counter | `method`, `endpoint`, `status` | Request count by method, path, status |
| `docex_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency distribution |
| `docex_errors_total` | Counter | `type` (ErrorCode) | Error count by error code |
| `docex_cache_ops_total` | Counter | `operation` (hit/miss), `type` (doc/search) | Cache hit/miss counts |
| `docex_db_pool_size` | Gauge | — | Current asyncpg connection pool size |

---

## 11. Web UI

DocEx includes a lightweight web UI served by Caddy.

Open `http://localhost` (or `http://<server-ip>` on a cloud deployment) in a browser.

**Tabs:**
- **Ingest** — Submit a new document (title, content, optional metadata)
- **Search** — Full-text search with paginated results; click a result to view details
- **Get Document** — Retrieve a document by UUID

The UI fetches from the same origin (no CORS needed since Caddy serves both UI and proxies API).

---

## Cleanup

```bash
# Stop all services
docker compose down

# Stop and delete all data volumes (PostgreSQL, ES, Kafka, Caddy)
docker compose down -v
```
