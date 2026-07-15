#!/usr/bin/env python3
"""Seed DocEx with documents from Stardew Valley Wiki."""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

import httpx

WIKI_API = "https://stardewvalleywiki.com/mediawiki/api.php"
USER_AGENT = "DocEx/0.1 (seed script)"
TENANT = "stardewvalley"
BATCH_SIZE = 50
REQUEST_DELAY = 0.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed")


# ── Wikitext stripping ──────────────────────────────────────────────

def strip_templates(text: str) -> str:
    """Remove MediaWiki template syntax ({{...}}) from wikitext.

    Args:
        text: Raw wikitext.

    Returns:
        Text with template markup stripped.
    """
    result = []
    depth = 0
    i = 0
    while i < len(text):
        if text[i : i + 2] == "{{":
            depth += 1
            i += 2
        elif text[i : i + 2] == "}}":
            depth = max(0, depth - 1)
            i += 2
        else:
            if depth == 0:
                result.append(text[i])
            i += 1
    return "".join(result)


def strip_tables(text: str) -> str:
    """Remove MediaWiki table markup ({| ... |}) from wikitext.

    Args:
        text: Raw wikitext.

    Returns:
        Text with table markup removed.
    """
    lines = text.split("\n")
    out = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{|"):
            in_table = True
            continue
        if stripped.startswith("|}") or stripped == "|}":
            in_table = False
            continue
        if not in_table:
            out.append(line)
    return "\n".join(out)


def strip_wikitext(wikitext: str) -> str:
    """Strip all WikiMedia markup from raw wikitext, returning plain text.

    Removes templates, tables, refs, comments, HTML tags, file links,
    wiki links, external links, heading markers, bold/italic, horizontal
    rules, list markers, and table cell markers.

    Args:
        wikitext: Raw MediaWiki source text.

    Returns:
        Clean plain text content.
    """
    text = wikitext

    text = strip_templates(text)

    text = strip_tables(text)

    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?ref[^>]*>", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)

    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    text = re.sub(
        r"\[\[(?:File|Image|Media|Category):[^\]]*\]\]", "", text, flags=re.IGNORECASE
    )

    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    text = re.sub(r"\[(https?://[^\s]+)\s+([^\]]+)\]", r"\2", text)
    text = re.sub(r"\[https?://[^\s\]]+\]", "", text)

    text = re.sub(r"^=+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*=+\s*$", "", text, flags=re.MULTILINE)

    text = text.replace("'''", "").replace("''", "")

    text = re.sub(r"^----+", "", text, flags=re.MULTILINE)

    text = re.sub(r"^[\*#:;]+", "", text, flags=re.MULTILINE)

    text = re.sub(r"^[|!].*", "", text, flags=re.MULTILINE)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)

    return text.strip()


# ── Wiki API ─────────────────────────────────────────────────────────

def make_client():
    """Create an async HTTP client configured with the seed user-agent."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    )


async def fetch_all_titles(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all page titles from the MediaWiki API via paginated allpages.

    Args:
        client: The async HTTP client.

    Returns:
        List of dicts with 'pageid' and 'title' keys.
    """
    titles = []
    apcontinue = None
    params = {
        "action": "query",
        "list": "allpages",
        "aplimit": "max",
        "format": "json",
    }

    while True:
        if apcontinue:
            params["apcontinue"] = apcontinue

        resp = await client.get(WIKI_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("query", {}).get("allpages", [])
        for p in pages:
            titles.append({"pageid": p["pageid"], "title": p["title"]})

        cont = data.get("continue", {})
        apcontinue = cont.get("apcontinue")
        if not apcontinue:
            break

        log.info("  listed %d pages so far...", len(titles))

    return titles


async def fetch_page_content(
    client: httpx.AsyncClient, batch: list[dict]
) -> list[dict]:
    """Fetch the raw wikitext content for a batch of pages by title.

    Args:
        client: The async HTTP client.
        batch: List of page dicts with 'title' keys.

    Returns:
        List of dicts with 'pageid', 'title', and 'content' keys.
    """
    titles_str = "|".join(p["title"] for p in batch)
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "titles": titles_str,
        "format": "json",
    }

    resp = await client.get(WIKI_API, params=params)
    resp.raise_for_status()
    data = resp.json()

    pages = data.get("query", {}).get("pages", {})
    results = []
    for pageid_str, page_data in pages.items():
        pageid = int(pageid_str) if pageid_str != "-1" else -1
        if pageid == -1:
            continue
        revisions = page_data.get("revisions", [])
        if not revisions:
            continue
        content = revisions[0].get("*", "")
        results.append(
            {
                "pageid": pageid,
                "title": page_data["title"],
                "content": content,
            }
        )
    return results


def make_document(title: str, content: str, pageid: int) -> dict:
    """Convert a wiki page to a DocEx document JSON payload.

    Strips wikitext and skips redirect pages.

    Args:
        title: Page title.
        content: Raw wikitext content.
        pageid: MediaWiki page ID.

    Returns:
        Document dict, or None if the page is a redirect or has no content.
    """
    plain = strip_wikitext(content)
    if not plain or plain.startswith("REDIRECT"):
        return None

    return {
        "title": title,
        "content": plain,
        "metadata": {
            "source": "stardewvalleywiki",
            "wiki_id": pageid,
            "wiki_url": f"https://stardewvalleywiki.com/{title.replace(' ', '_')}",
        },
    }


# ── Output ───────────────────────────────────────────────────────────

def write_jsonl(docs: list[dict], path: Path):
    """Write a list of document dicts to a JSONL file.

    Args:
        docs: List of document dicts (None entries are skipped).
        path: Output file path.
    """
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for doc in docs:
            if doc:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                count += 1
    log.info("Wrote %d documents to %s", count, path)


async def post_to_api(docs: list[dict], api_url: str):
    """POST documents to the DocEx API sequentially.

    Args:
        docs: List of document dicts.
        api_url: Base URL of the DocEx API.
    """
    count = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for doc in docs:
            if not doc:
                continue
            try:
                resp = await client.post(
                    f"{api_url}/api/v1/documents",
                    headers={"X-Tenant-ID": TENANT, "Content-Type": "application/json"},
                    json=doc,
                )
                resp.raise_for_status()
                count += 1
            except httpx.HTTPStatusError as e:
                log.warning("  failed to post '%s': %s", doc["title"], e.response.status_code)
            if count % 100 == 0:
                log.info("  posted %d documents...", count)
    log.info("Posted %d documents to %s", count, api_url)


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    """Main entry point: fetch wiki pages, extract content, output JSONL and/or POST to API."""
    parser = argparse.ArgumentParser(description="Seed DocEx with Stardew Valley Wiki data")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--api",
        help="Base URL of the DocEx API (e.g. http://localhost)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Delay between API requests in seconds (default: {REQUEST_DELAY})",
    )
    args = parser.parse_args()

    if not args.output and not args.api:
        parser.error("Specify --output or --api")

    print("Fetching page list from Stardew Valley Wiki...")
    async with make_client() as client:
        titles = await fetch_all_titles(client)
    log.info("Found %d pages", len(titles))

    docs = []
    async with make_client() as client:
        for i in range(0, len(titles), BATCH_SIZE):
            batch = titles[i : i + BATCH_SIZE]
            log.info(
                "Fetching content %d-%d of %d...",
                i + 1,
                min(i + BATCH_SIZE, len(titles)),
                len(titles),
            )
            pages = await fetch_page_content(client, batch)
            for p in pages:
                doc = make_document(p["title"], p["content"], p["pageid"])
                docs.append(doc)
            await asyncio.sleep(args.delay)

    total = sum(1 for d in docs if d)
    log.info("Extracted %d documents from %d pages", total, len(docs))

    if args.output:
        write_jsonl(docs, args.output)

    if args.api:
        log.info("Posting to %s...", args.api)
        await post_to_api(docs, args.api)

    print(f"Done — {total} documents generated.")


if __name__ == "__main__":
    asyncio.run(main())
