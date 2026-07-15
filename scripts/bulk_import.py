#!/usr/bin/env python3
"""Bulk-import seed data from a JSONL file into the DocEx API."""

import argparse
import asyncio
import json
import logging
import sys
import time

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bulk_import")

BATCH_SIZE = 50
MAX_RETRIES = 5
BACKOFF_BASE = 1.0
DEFAULT_RATE = 100


async def post_with_retry(client: httpx.AsyncClient, url: str, doc: dict, tenant: str) -> httpx.Response | Exception:
    """POST a document to the API with exponential backoff retry on 429 responses.

    Args:
        client: The async HTTP client.
        url: Full API URL for POST /api/v1/documents.
        doc: Document payload dict.
        tenant: Tenant ID for the X-Tenant-ID header.

    Returns:
        The HTTP response if successful, or the last exception/response after retries.
    """
    headers = {"X-Tenant-ID": tenant, "Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(url, headers=headers, json=doc)
            if resp.status_code != 429:
                return resp
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning("  429 on '%s' (attempt %d/%d), retrying in %.1fs...", doc["title"], attempt + 1, MAX_RETRIES, wait)
            await asyncio.sleep(wait)
        except httpx.ConnectError as e:
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning("  connect error on '%s' (attempt %d/%d), retrying in %.1fs...", doc["title"], attempt + 1, MAX_RETRIES, wait)
            await asyncio.sleep(wait)
        except Exception as e:
            return e
    try:
        return await client.post(url, headers=headers, json=doc)
    except Exception as e:
        return e


async def import_via_api(docs: list[dict], api_url: str, tenant: str, batch: int, max_docs: int | None, rate: int = DEFAULT_RATE):
    """POST documents to the DocEx API in concurrent batches via HTTP.

    Retries individual documents on 429 (rate limit) and connect errors
    with exponential backoff.  Uses a token-bucket-style throttle to keep
    the average request rate at ``rate`` req/s.

    Args:
        docs: List of document dicts to import.
        api_url: Base URL of the DocEx API.
        tenant: Tenant ID for the X-Tenant-ID header.
        batch: Number of concurrent POST requests per batch.
        max_docs: Optional cap on the number of documents to import.
        rate: Target maximum requests per second.

    Returns:
        Tuple of (success_count, error_count).
    """
    success = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(docs), batch):
            chunk_start = time.monotonic()
            chunk = docs[i : i + batch]
            tasks = [
                post_with_retry(client, f"{api_url}/api/v1/documents", doc, tenant)
                for doc in chunk
            ]
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

            elapsed = time.monotonic() - chunk_start
            min_duration = len(chunk) / rate
            if elapsed < min_duration:
                await asyncio.sleep(min_duration - elapsed)

            pct = (i + len(chunk)) / len(docs) * 100
            log.info("  %d/%d (%.0f%%) | success=%d errors=%d", min(i + batch, len(docs)), len(docs), pct, success, errors)

    return success, errors


async def main():
    """Load documents from a JSONL file and import them into the DocEx API."""
    parser = argparse.ArgumentParser(description="Bulk-import seed data into DocEx")
    parser.add_argument("input", help="Path to JSONL file")
    parser.add_argument("--api", default="http://localhost", help="API base URL")
    parser.add_argument("--tenant", default="stardewvalley", help="Tenant ID")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Documents per batch")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE, help="Target max requests per second (default %d)" % DEFAULT_RATE)
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

    success, errors = await import_via_api(docs, args.api, args.tenant, args.batch, args.max, args.rate)

    log.info("Done — %d imported, %d errors", success, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
