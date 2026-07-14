from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://docsextract:docsextract@localhost:5432/docex"
    redis_url: str = "redis://localhost:6379/0"

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

    fts_language: str = "english"
    fts_rank_normalization: int = 0
    fts_rank_weights: str = "{0.05,0.05,0.05,1.0}"

    debug: bool = False
    redis_decode_responses: bool = True

    version: str = "0.1.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
