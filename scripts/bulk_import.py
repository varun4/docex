#!/usr/bin/env python3
"""Bulk-import seed data from a JSONL file into the DocExtract API."""

import argparse
import asyncio
import json
import logging
import sys

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bulk_import")

BATCH_SIZE = 50


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


async def main():
    parser = argparse.ArgumentParser(description="Bulk-import seed data into DocExtract")
    parser.add_argument("input", help="Path to JSONL file")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--tenant", default="stardewvalley", help="Tenant ID")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Documents per batch")
    parser.add_argument("--max", type=int, help="Max documents to import")
    args = parser.parse_args()

    docs = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))

    if args.max:
        docs = docs[: args.max]

    log.info("Loaded %d documents from %s", len(docs), args.input)

    success, errors = await import_via_api(docs, args.api, args.tenant, args.batch, args.max)

    log.info("Done — %d imported, %d errors", success, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
