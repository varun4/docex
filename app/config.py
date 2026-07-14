"""Application configuration loaded from environment variables and .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for all runtime parameters (DB, ES, Kafka, rate limits, cache)."""
    database_url: str = "postgresql://docsextract:docsextract@localhost:5432/docex"
    redis_url: str = "redis://localhost:6379/0"
    elasticsearch_url: str = "http://localhost:9200"
    es_index_name: str = "documents"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "documents.ingest"
    kafka_group_id: str = "documents-ingest-consumer"

    rate_limit_search: int = 100
    rate_limit_index: int = 10
    rate_limit_global: int = 1000
    rate_limit_window_ms: int = 1000
    rate_limit_redis_ttl: int = 2

    cache_ttl_doc: int = 300
    cache_ttl_search: int = 60
    cache_scan_count: int = 100

    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_query_timeout: int = 5
    max_content_length: int = 1_048_576

    search_default_page: int = 1
    search_default_size: int = 20
    search_max_size: int = 100

    debug: bool = False
    redis_decode_responses: bool = True

    version: str = "0.1.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
