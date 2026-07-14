#!/usr/bin/env python3
"""Create the outbox schema if it doesn't exist."""

import argparse
import asyncio
import logging
import os

import asyncpg

from app.config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("init_db")
settings = Settings()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id    TEXT NOT NULL,
    doc_id       UUID,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',
    event_type   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_status
    ON document_events (status, created_at);

CREATE INDEX IF NOT EXISTS idx_outbox_tenant
    ON document_events (tenant_id, event_id);
"""


async def main():
    """Create the outbox table and indexes if they don't exist in PostgreSQL."""
    parser = argparse.ArgumentParser(description="Initialize the outbox schema")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", settings.database_url),
        help="PostgreSQL connection URL",
    )
    args = parser.parse_args()

    log.info("Connecting to %s", args.db_url)
    conn = await asyncpg.connect(args.db_url)
    try:
        await conn.execute(SCHEMA_SQL)
        log.info("Outbox schema created successfully")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
