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

MAX_SUMMARY = 20_000
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
# Sections a trope hunter wants first; sections that never help and are dropped.
FIRST = ("plot", "story", "synopsis", "premise", "summary", "overview", "setting", "character", "theme", "narrative", "ending")
SKIP = (
    "reference",
    "external link",
    "navigation",
    "see also",
    "gallery",
    "video",
    "trivia",
    "reception",
    "development",
    "release",
    "marketing",
    "sales",
    "legacy",
    "soundtrack",
    "credits",
    "award",
    "production",
    "merchandise",
    "behind the scenes",
    "notes",
)
FANDOM_URL_RX = re.compile(r"^https?://([a-z0-9-]+)\.fandom\.com/wiki/([^?#]+)")


def page_sections(html: str) -> list[tuple[str, str]]:
    """A rendered wiki page as (heading, text) sections, the intro first with an empty heading; no tables or boxes."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".mw-parser-output") or soup
    for tag in root.select(DROP):
        tag.decompose()
    sections: list[tuple[str, list[str]]] = [("", [])]
    for el in root.find_all(["h2", "h3", "h4", "p", "li", "dd"]):
        text = " ".join(el.get_text(" ").split())
        if not text:
            continue
        if el.name == "h2":
            sections.append((text, []))
        elif el.name in ("h3", "h4"):
            sections[-1][1].append(f"\n{text}:")
        else:
            sections[-1][1].append(text)
    return [(h, "\n".join(lines).strip()) for h, lines in sections if lines]


def html_to_text(html: str, cap: int = MAX_SUMMARY) -> str:
    """Plot, story and character sections first, the rest after, nothing from reception or development;
    the cap falls on the least useful part."""
    secs = page_sections(html)

    def rank(h: str) -> int:
        low = h.lower()
        if not low:
            return 0
        if any(k in low for k in FIRST):
            return 1
        return 2

    kept = [(h, t) for h, t in secs if not any(k in h.lower() for k in SKIP)]
    kept.sort(key=lambda ht: rank(ht[0]))
    out: list[str] = []
    used = 0
    for h, t in kept:
        block = f"\n{h}:\n{t}" if h else t
        if used + len(block) > cap:
            if used == 0:
                out.append(block[:cap])
            break
        out.append(block)
        used += len(block)
    return "\n".join(out).strip()


def link_ref(url: str) -> tuple[str, str] | None:
    """A Fandom article URL the owner linked by hand as (wiki, title)."""
    m = FANDOM_URL_RX.match(url or "")
    return (m.group(1), m.group(2)) if m else None


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
        linked = any(link_ref(x.get("url") or "") for x in (m.get("links") or []))
        if not linked and (not m.get("wikidataId") or m.get("identity") != "pinned"):
            continue
        if wanted and m["id"] not in wanted:
            continue
        if not wanted and any(n.get("source") == "wiki" for n in (m.get("notes") or [])):
            continue
        todo.append(m)
    f = Fetcher(cache_dir=settings.lookup_cache_dir, user_agent=settings.user_agent)
    try:
        ents = wikidata.entities(f, [m["wikidataId"] for m in todo if m.get("wikidataId")])
        notes: list[dict[str, Any]] = []
        transcripts = 0
        no_article = 0
        ctx.progress(0, len(todo), "fandom")
        for n, m in enumerate(todo, 1):
            # A link the owner added on the work's page wins over Wikidata's id.
            refs = [r for r in (link_ref(x.get("url") or "") for x in (m.get("links") or [])) if r]
            refs += [r for r in map(fandom_ref, wikidata._strings(ents.get(m.get("wikidataId") or "", {}), "P6262")) if r]
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
