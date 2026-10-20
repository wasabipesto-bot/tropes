"""The owner's own writing about a work, from the Tumblr archive search (midden)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from .llm import LLM
from .schemas import NotesFilterOut
from .settings import Settings

log = logging.getLogger("tropes_worker.notes")


def search_posts(settings: Settings, title: str, limit: int = 20) -> list[dict[str, Any]]:
    """Posts from the owner's blog that mention the quoted title. Empty when no key is configured."""
    if not settings.midden_key:
        return []
    q = f'"{title}" blog:{settings.midden_blog}'
    try:
        r = httpx.get(
            settings.midden_url,
            params={"q": q, "format": "text", "page_size": limit},
            headers={"x-api-key": settings.midden_key, "User-Agent": "tropes-worker"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001 - notes are optional; a search failure must not fail a dossier
        log.warning("midden search for %r failed: %s", title, e)
        return []
    hits = data.get("hits") or []
    out = []
    for h in hits:
        text = h.get("body") or h.get("text") or ""
        if not text.strip():
            continue
        out.append({"url": h.get("url") or h.get("post_url") or h.get("link"), "text": re.sub(r"\s+", " ", text).strip()[:4000]})
    return out


async def relevant_notes(llm: LLM, entry: str, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the posts the model judges to be about the work. Shortened titles and reblogs count."""
    if not posts:
        return []
    listing = "\n\n".join(f"[{i}] {p['text'][:1200]}" for i, p in enumerate(posts))
    verdict = await llm.complete("notes_filter", {"entry": entry, "posts": listing}, NotesFilterOut)
    keep = {v.index for v in verdict.items if v.about_the_work}
    return [p for i, p in enumerate(posts) if i in keep]
