"""Background Kafka consumer entry point: polls documents.ingest, indexes to ES, warms cache, updates outbox."""

import asyncio
import json
import logging

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaConsumer
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from consumer.indexer import Indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("consumer")

settings = Settings()


async def main():
    """Run the Kafka consumer loop.

    Connects to Kafka, PostgreSQL, Redis, and Elasticsearch.
    Polls the `documents.ingest` topic and delegates to Indexer for each message.
    Handles graceful shutdown on CancelledError.
    """
    log.info("Starting consumer (group=%s, topic=%s)", settings.kafka_group_id, settings.kafka_topic)

    pg_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    redis = aioredis.from_url(settings.redis_url, decode_responses=settings.redis_decode_responses)
    es = AsyncElasticsearch(settings.elasticsearch_url)

    indexer = Indexer(es, redis, pg_pool)

    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_group_id,
        value_deserializer=lambda v: json.loads(v.decode()),
        key_deserializer=lambda k: k.decode() if k else None,
        auto_offset_reset="earliest",
    )

    try:
        await consumer.start()
        log.info("Kafka consumer started")

        async for msg in consumer:
            log.debug("Received event key=%s offset=%d", msg.key, msg.offset)
            await indexer.process_event(msg.value)

    except asyncio.CancelledError:
        log.info("Consumer shutting down...")
    finally:
        await consumer.stop()
        await pg_pool.close()
        await redis.close()
        await es.close()
        log.info("Consumer stopped")


if __name__ == "__main__":
    asyncio.run(main())
