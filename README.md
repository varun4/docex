# DocExtract — Distributed Document Search Service

A prototype distributed document search service with multi-tenancy, full-text search, caching, and rate limiting. Built with FastAPI, PostgreSQL FTS, and Redis.

## Prerequisites

- [Docker](https://docs.docker.com/engine/install/) + [Docker Compose](https://docs.docker.com/compose/install/)
- Internet connection (for initial seed data fetch and image pulls)

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url>
cd docex
cp .env.example .env

# 2. Start infrastructure (PostgreSQL + Redis)
docker compose up -d postgres redis

# 3. Create database schema
docker compose run app python scripts/init_db.py

# 4. Fetch seed data from Stardew Valley Wiki (~2,800 articles)
docker compose run app python scripts/seed.py --output data/seed.jsonl

# 5. Import seed data directly into PostgreSQL
docker compose run app python scripts/bulk_import.py data/seed.jsonl \
  --db-url postgresql://docsextract:docsextract@postgres:5432/docex

# 6. Start the API server with live reload
docker compose up app
```

The API is now available at `http://localhost:8000`.

## Usage

```bash
# Search documents
curl "http://localhost:8000/search?q=stardrop&page=1&size=10" \
  -H "X-Tenant-ID: stardewvalley"

# Get document by ID
curl "http://localhost:8000/documents/<id>" \
  -H "X-Tenant-ID: stardewvalley"

# Delete document
curl -X DELETE "http://localhost:8000/documents/<id>" \
  -H "X-Tenant-ID: stardewvalley"

# Health check
curl http://localhost:8000/health
```

## Scripts

| Script | Purpose |
|---|---|
| `scripts/seed.py` | Fetches pages from a MediaWiki API → JSONL |
| `scripts/bulk_import.py` | Imports JSONL → API (`--api`) or direct to DB (`--db-url`) |
| `scripts/init_db.py` | Creates/updates database schema (idempotent) |

## Project Structure

```
docex/
├── app/                    # FastAPI application
│   ├── main.py
│   ├── config.py
│   ├── routers/            # API endpoints
│   ├── schemas/            # Pydantic models
│   ├── services/           # Business logic
│   └── repositories/       # Data access (PostgreSQL + Redis)
├── scripts/                # Utility scripts
│   ├── seed.py
│   ├── bulk_import.py
│   └── init_db.py
├── data/                   # Generated seed data (gitignored)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/documents` | `X-Tenant-ID` | Index a new document |
| GET | `/search?q=&page=&size=` | `X-Tenant-ID` | Full-text search |
| GET | `/documents/{id}` | `X-Tenant-ID` | Get document details |
| DELETE | `/documents/{id}` | `X-Tenant-ID` | Delete a document |
| GET | `/health` | — | Health check with dependency status |
| POST | `/documents/bulk` | `X-Tenant-ID` | Bulk index documents |
| GET | `/metrics` | — | Prometheus metrics (request count, duration, cache hit ratio, errors, pool size) |

## Production Readiness

Features implemented to improve production readiness:

| Feature | Description |
|---|---|
| **Request ID** | `X-Request-ID` header injected into every response for request tracing |
| **Rate limit headers** | `X-RateLimit-Limit` and `X-RateLimit-Remaining` returned on all rate-limited routes |
| **Prometheus metrics** | `/metrics` endpoint exposes request counts, duration histogram, cache hit/miss, connection pool size, and error counts |
| **Structured error codes** | All errors use `ErrorCode` enum (`/app/enums.py`), returned as `{"error": {"code": ..., "message": ..., "detail": ...}}` |
| **Configurable via env** | Rate limits, cache TTLs, pool sizes, FTS language, and feature flags all configurable through `.env` |
| **Bulk indexing** | `POST /documents/bulk` for batch document ingestion |
| **Graceful degradation** | Health check reports per-dependency status with latency |

See `.env.example` for all available configuration options.
