#!/usr/bin/env python3
"""Bulk-import seed data from a JSONL file into the DocExtract API or directly to PostgreSQL."""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

import asyncpg
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bulk_import")

BATCH_SIZE = 50

INSERT_SQL = """
INSERT INTO documents (id, tenant_id, title, content, metadata)
VALUES ($1, $2, $3, $4, $5::jsonb)
"""


async def import_via_api(docs: list[dict], api_url: str, tenant: str, batch: int, max_docs: int | None):
    success = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(docs), batch):
            chunk = docs[i : i + batch]
            tasks = []
            for doc in chunk:
                tasks.append(
                    client.post(
                        f"{api_url}/documents",
                        headers={
                            "X-Tenant-ID": tenant,
                            "Content-Type": "application/json",
                        },
                        json=doc,
                    )
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for doc, result in zip(chunk, results):
                if isinstance(result, Exception):
                    log.warning("  failed '%s': %s", doc["title"], result)
                    errors += 1
                elif result.status_code >= 400:
                    log.warning("  failed '%s': HTTP %d", doc["title"], result.status_code)
                    errors += 1
                else:
                    success += 1

            pct = (i + len(chunk)) / len(docs) * 100
            log.info("  %d/%d (%.0f%%) | success=%d errors=%d", min(i + batch, len(docs)), len(docs), pct, success, errors)

    return success, errors


async def import_via_db(docs: list[dict], db_url: str, tenant: str, max_docs: int | None):
    success = 0
    errors = 0

    conn = await asyncpg.connect(db_url)
    try:
        for i, doc in enumerate(docs):
            if max_docs and i >= max_docs:
                break
            try:
                await conn.execute(
                    INSERT_SQL,
                    uuid.uuid4(),
                    tenant,
                    doc["title"],
                    doc["content"],
                    json.dumps(doc.get("metadata", {})),
                )
                success += 1
            except Exception as e:
                log.warning("  failed '%s': %s", doc["title"], e)
                errors += 1

            if (i + 1) % 500 == 0:
                log.info("  %d/%d | success=%d errors=%d", i + 1, min(max_docs or len(docs), len(docs)), success, errors)
    finally:
        await conn.close()

    return success, errors


async def main():
    parser = argparse.ArgumentParser(description="Bulk-import seed data into DocExtract")
    parser.add_argument("input", help="Path to JSONL file")
    parser.add_argument("--api", help="API base URL (e.g. http://localhost:8000)")
    parser.add_argument("--db-url", help="PostgreSQL URL for direct DB import (bypasses API)")
    parser.add_argument("--tenant", default="stardewvalley", help="Tenant ID")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Documents per batch")
    parser.add_argument("--max", type=int, help="Max documents to import")
    args = parser.parse_args()

    if not args.api and not args.db_url:
        parser.error("Specify --api or --db-url")

    docs = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))

    if args.max:
        docs = docs[: args.max]

    log.info("Loaded %d documents from %s", len(docs), args.input)

    if args.api:
        success, errors = await import_via_api(docs, args.api, args.tenant, args.batch, args.max)
    else:
        success, errors = await import_via_db(docs, args.db_url, args.tenant, args.max)

    log.info("Done — %d imported, %d errors", success, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
