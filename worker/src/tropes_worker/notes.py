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


SMALL = {"a", "an", "and", "of", "the", "to", "in", "on", "at", "for", "&"}


def title_aliases(title: str, extra: str | list[str] | None = None) -> list[str]:
    """Names the owner's posts might use instead of the full title: the initialism of a title of three or more
    words (DGHDA, TLT, GotG), the part after a colon (Edgerunners), and anything the owner typed as aliases."""
    out: list[str] = []
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9']*", title)
    if len(words) >= 3:
        initials = "".join(w[0] for w in words)
        if len(initials) >= 3:
            out.append(initials.upper())
    if ":" in title:
        tail = title.split(":", 1)[1].strip()
        if len(tail) >= 4 and not re.fullmatch(r"[\d\s]+", tail):
            out.append(tail)
    typed = extra.split(",") if isinstance(extra, str) else list(extra or [])
    out += [a.strip() for a in typed if a and a.strip()]
    seen: set[str] = set()
    return [a for a in out if a.lower() != title.lower() and not (a.lower() in seen or seen.add(a.lower()))]


def search_posts(settings: Settings, title: str, aliases: list[str] | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Posts from the owner's blog that quote the title or one of its aliases. Empty when no key is configured."""
    if not settings.midden_key:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in [title, *(aliases or [])]:
        q = f'"{name}" blog:{settings.midden_blog}'
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
            log.warning("midden search for %r failed: %s", name, e)
            continue
        for h in data.get("hits") or []:
            text = h.get("body") or h.get("text") or ""
            url = h.get("url") or h.get("post_url") or h.get("link")
            key = url or text[:200]
            if not text.strip() or key in seen:
                continue
            seen.add(key)
            out.append({"url": url, "text": re.sub(r"\s+", " ", text).strip()[:4000]})
    return out


async def relevant_notes(llm: LLM, entry: str, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the posts the model judges to be about the work. Shortened titles and reblogs count."""
    if not posts:
        return []
    listing = "\n\n".join(f"[{i}] {p['text'][:1200]}" for i, p in enumerate(posts))
    verdict = await llm.complete("notes_filter", {"entry": entry, "posts": listing}, NotesFilterOut)
    keep = {v.index for v in verdict.items if v.about_the_work}
    return [p for i, p in enumerate(posts) if i in keep]
