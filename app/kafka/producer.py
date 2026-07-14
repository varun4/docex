import json

from aiokafka import AIOKafkaProducer

from app.schemas.events import DocumentEvent


async def publish_event(
    kafka_producer: AIOKafkaProducer,
    topic: str,
    event: DocumentEvent,
):
    payload = event.model_dump()
    payload["timestamp"] = payload["timestamp"].isoformat()
    payload["doc_id"] = str(payload["doc_id"])
    payload["event_id"] = str(payload["event_id"])
    await kafka_producer.send(
        topic=topic,
        key=event.tenant_id.encode(),
        value=json.dumps(payload, default=str).encode(),
    )
