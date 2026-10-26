"""fetch_wiki: Fandom article summaries, and transcripts where a wiki keeps them, for pinned works (plan T12).

Runs on the model worker and makes no model calls. Payload {mediaIds?, auto}: without ids, every pinned work
with a Wikidata item and no wiki note yet. The article's plain text (TextExtracts) becomes a media_note with
source `wiki` that the dossier prompt reads; an `<Article>/Transcript` page, when one exists and is long
enough, is saved under the sources dir and linked as a text source. Polite: one request a second per wiki,
cached like the lookups.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..lookup import wikidata
from ..lookup.http import Fetcher
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.fetch_wiki")

MAX_SUMMARY = 12_000
MIN_SUMMARY = 200
MIN_TRANSCRIPT = 2_000


def fandom_ref(value: str) -> tuple[str, str] | None:
    """A Wikidata P6262 value ("arcane:Arcane", "de.arcane:Arcane") as (wiki subdomain, article title), English only."""
    wiki, sep, title = value.partition(":")
    # A dotted prefix ("de.", "pt-br.") is a language edition; the English wiki is the bare subdomain.
    if not sep or not title or not re.fullmatch(r"[a-z0-9-]+", wiki):
        return None
    return wiki, title.replace(" ", "_")


DROP = ", ".join(
    ["script", "style", "table", ".navbox", ".portable-infobox", ".infobox", ".toc", ".reference", ".mw-editsection"]
    + [".gallery", ".noprint", "figure", ".thumb", "sup"]
)


def html_to_text(html: str) -> str:
    """A rendered wiki page as plain text: headings on their own lines, paragraphs and list items, no tables or boxes."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".mw-parser-output") or soup
    for tag in root.select(DROP):
        tag.decompose()
    lines: list[str] = []
    for el in root.find_all(["h2", "h3", "h4", "p", "li", "dd"]):
        text = " ".join(el.get_text(" ").split())
        if not text:
            continue
        if el.name in ("h2", "h3", "h4"):
            if text.lower() in ("references", "external links", "navigation", "see also", "gallery", "videos", "trivia"):
                break
            lines.append(f"\n{text}:")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


def page_text(f: Fetcher, wiki: str, title: str) -> str | None:
    """The plain text of a page, or None when it does not exist. Fandom has no TextExtracts, so this renders the
    page through action=parse and strips the HTML."""
    d = f.get_json(
        f"https://{wiki}.fandom.com/api.php",
        {"action": "parse", "page": title, "prop": "text", "redirects": 1, "disablelimitreport": 1, "format": "json"},
    )
    if not d or "error" in d:
        return None
    html = ((d.get("parse") or {}).get("text") or {}).get("*") or ""
    return html_to_text(html)


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    wanted = set(payload.get("mediaIds") or [])
    media = ctx.client.subjects()["media"]
    todo = []
    for m in media:
        if not m.get("wikidataId") or m.get("identity") != "pinned":
            continue
        if wanted and m["id"] not in wanted:
            continue
        if not wanted and any(n.get("source") == "wiki" for n in (m.get("notes") or [])):
            continue
        todo.append(m)
    f = Fetcher(cache_dir=settings.lookup_cache_dir, user_agent=settings.user_agent)
    try:
        ents = wikidata.entities(f, [m["wikidataId"] for m in todo])
        notes: list[dict[str, Any]] = []
        transcripts = 0
        no_article = 0
        ctx.progress(0, len(todo), "fandom")
        for n, m in enumerate(todo, 1):
            refs = [r for r in map(fandom_ref, wikidata._strings(ents.get(m["wikidataId"], {}), "P6262")) if r]
            if not refs:
                no_article += 1
                continue
            wiki, title = refs[0]
            text = page_text(f, wiki, title)
            if text and len(text) >= MIN_SUMMARY:
                notes.append(
                    {
                        "mediaId": m["id"],
                        "source": "wiki",
                        "label": "Fandom",
                        "url": f"https://{wiki}.fandom.com/wiki/{title}",
                        "text": text[:MAX_SUMMARY],
                    }
                )
            transcript = page_text(f, wiki, f"{title}/Transcript")
            if transcript and len(transcript) >= MIN_TRANSCRIPT:
                rel = f"web/fandom/{m['id']}.txt"
                path = settings.sources_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# Transcript\n{transcript}\n", encoding="utf-8")
                ctx.client.link_text(m["id"], rel, "Fandom transcript")
                transcripts += 1
            if n % 10 == 0:
                ctx.progress(n, len(todo), "fandom")
        ctx.progress(len(todo), len(todo), "done")
        return {
            "summary": {
                "works": len(todo),
                "articles": len(notes),
                "transcripts": transcripts,
                "noArticle": no_article,
                "requests": f.requests_made,
            },
            "notes": notes,
            "warnings": f.warnings[:50],
        }
    finally:
        f.close()
