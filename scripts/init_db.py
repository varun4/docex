#!/usr/bin/env python3
"""Create the database schema if it doesn't exist."""

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


def make_schema(fts_language: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{{}}',
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('{fts_language}', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('{fts_language}', coalesce(content, '')), 'B')
    ) STORED,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_search
    ON documents
    USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_documents_tenant
    ON documents (tenant_id, id);
"""


async def main():
    parser = argparse.ArgumentParser(description="Initialize the database schema")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", settings.database_url),
        help="PostgreSQL connection URL",
    )
    args = parser.parse_args()

    log.info("Connecting to %s", args.db_url)
    conn = await asyncpg.connect(args.db_url)
    try:
        await conn.execute(make_schema(settings.fts_language))
        log.info("Schema created successfully (fts_language=%s)", settings.fts_language)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
