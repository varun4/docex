"""Async Kafka producer for publishing document events to the ingest topic."""

import json

from aiokafka import AIOKafkaProducer

from app.schemas.events import DocumentEvent


async def publish_event(
    kafka_producer: AIOKafkaProducer,
    topic: str,
    event: DocumentEvent,
):
    """Serialize and publish a DocumentEvent to the given Kafka topic.

    Uses tenant_id as the message key for ordered per-tenant processing.

    Args:
        kafka_producer: The AIOKafka producer instance.
        topic: Target Kafka topic name.
        event: The DocumentEvent to publish.
    """
    payload = event.model_dump()
    payload["timestamp"] = payload["timestamp"].isoformat()
    payload["doc_id"] = str(payload["doc_id"])
    payload["event_id"] = str(payload["event_id"])
    await kafka_producer.send(
        topic=topic,
        key=event.tenant_id.encode(),
        value=json.dumps(payload, default=str).encode(),
    )
