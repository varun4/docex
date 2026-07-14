"""Prometheus metric definitions for request count, duration, cache ops, pool size, and errors."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter(
    "docex_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
"""Total HTTP request count, labelled by method, endpoint path, and response status."""

REQUEST_DURATION = Histogram(
    "docex_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

CACHE_OPS = Counter(
    "docex_cache_operations_total",
    "Cache operations",
    ["operation", "type"],
)

DB_POOL_SIZE = Gauge(
    "docex_db_pool_size",
    "Database connection pool size",
)

ERRORS = Counter(
    "docex_errors_total",
    "Application errors by type",
    ["type"],
)
