"""Read the owner's Media Log through Notion's API and hand the rows to the site.

The key lives on the worker; the site never calls Notion. Rows are mapped to the
same shape the site's CSV importer produces (web/src/lib/notion-import.ts
LogRow), then posted to POST /api/import/notion, which runs the upsert and
queues follow-up jobs for new entries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .settings import Settings

log = logging.getLogger("tropes_worker.notion")

NOTION_VERSION = "2025-09-03"
NUMBER_PROPS = {"medium": "Medium", "story": "Story", "tone": "Tone", "enjoyability": "Enjoyability", "effect": "Effect"}


def _plain(rich: list[dict[str, Any]] | None) -> str:
    return "".join(part.get("plain_text", "") for part in rich or []).strip()


def row_from_page(page: dict[str, Any]) -> dict[str, Any] | None:
    """One Notion page → LogRow dict, or None when it has no title or type."""
    props = page.get("properties") or {}

    def prop(name: str) -> dict[str, Any]:
        return props.get(name) or {}

    title = _plain(prop("Title").get("title"))
    type_ = (prop("Type").get("select") or {}).get("name")
    if not title or not type_:
        return None
    date = (prop("Date").get("date") or {}).get("start")
    ratings = {key: prop(label).get("number") for key, label in NUMBER_PROPS.items()}
    return {
        "notionId": page["id"].replace("-", ""),
        "title": title,
        "type": type_,
        "creator": _plain(prop("Artist/Developer").get("rich_text")) or None,
        "loggedDate": date[:10] if date else None,
        "ratings": ratings,
        "imageUrl": prop("Image Link").get("url") or None,
        "mediaUrl": prop("Media Link").get("url") or None,
    }


def fetch_rows(settings: Settings) -> list[dict[str, Any]]:
    """Every row of the Media Log, in Notion's order. Trashed pages are not returned by the query."""
    if not settings.notion_api_key:
        raise RuntimeError("NOTION_API_KEY is not set")
    headers = {
        "Authorization": f"Bearer {settings.notion_api_key}",
        "Notion-Version": NOTION_VERSION,
        "User-Agent": "tropes-worker",
    }
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    with httpx.Client(timeout=60) as http:
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            url = f"https://api.notion.com/v1/data_sources/{settings.notion_data_source}/query"
            r = http.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            for page in data.get("results", []):
                row = row_from_page(page)
                if row:
                    rows.append(row)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    log.info("notion: %d rows", len(rows))
    return rows
