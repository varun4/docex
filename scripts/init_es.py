#!/usr/bin/env python3
"""Create the Elasticsearch index with mapping if it doesn't exist."""

import argparse
import asyncio
import logging
import os

from elasticsearch import AsyncElasticsearch

from app.config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("init_es")
settings = Settings()

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "doc_id":       {"type": "keyword"},
            "tenant_id":    {"type": "keyword"},
            "content_hash": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "english",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "content":      {"type": "text", "analyzer": "english"},
            "metadata":     {"type": "object", "enabled": False},
            "created_at":   {"type": "date"},
            "updated_at":   {"type": "date"},
        }
    },
}


async def main():
    """Create the Elasticsearch index with the defined mapping if it doesn't already exist."""
    parser = argparse.ArgumentParser(description="Initialize Elasticsearch index")
    parser.add_argument(
        "--es-url",
        default=os.getenv("ELASTICSEARCH_URL", settings.elasticsearch_url),
        help="Elasticsearch URL",
    )
    args = parser.parse_args()

    es = AsyncElasticsearch(args.es_url)
    try:
        exists = await es.indices.exists(index=settings.es_index_name)
        if exists:
            log.info("Index '%s' already exists", settings.es_index_name)
        else:
            await es.indices.create(index=settings.es_index_name, body=INDEX_MAPPING)
            log.info("Index '%s' created successfully", settings.es_index_name)
    finally:
        await es.close()


if __name__ == "__main__":
    asyncio.run(main())
