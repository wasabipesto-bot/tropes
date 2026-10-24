"""Scores read from a work's own page on Rotten Tomatoes, Metacritic and Goodreads.

Only at the exact path Wikidata (or the owner) supplies, never a site search; one request per page, cached by
the Fetcher. The number comes from JSON the page embeds (its own component data, or schema.org JSON-LD for search
engines), not from the visible markup. Any miss (no page, no block, no score yet) is None.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from .http import Fetcher
from .models import Link

HTML = {"Accept": "text/html"}

_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_SEGMENT = re.compile(r"[\w.~%:-]+")


def rotten_tomatoes(f: Fetcher, path: str) -> Link | None:
    """Tomatometer (critics, all reviews). Path as Wikidata P1258 gives it: "tv/pantheon", "m/dune_part_two"."""
    clean = _path(path)
    if clean is None:
        return None
    url = f"https://www.rottentomatoes.com/{clean}"
    html = f.get_text(url, headers=HTML)
    if html is None:
        return None
    card = _block(html, "media-scorecard-json")
    critics = card.get("criticsScore") if isinstance(card, dict) else None
    value = _num(critics.get("score")) if isinstance(critics, dict) else None
    if value is None:
        value = _num(_ld_rating(html, "Tomatometer").get("ratingValue"))
    if value is None or not 0 <= value <= 100:
        return None
    return Link(url=url, score=f"{value:.0f}%", score_value=value)


def metacritic(f: Fetcher, path: str) -> Link | None:
    """Metascore. Path as Wikidata P1712 gives it: "tv/pantheon", "movie/dune-part-two", "game/control"."""
    clean = _path(path)
    if clean is None:
        return None
    # The site's canonical URLs end in a slash; asking for that saves a redirect hop.
    url = f"https://www.metacritic.com/{clean}/"
    html = f.get_text(url, headers=HTML)
    if html is None:
        return None
    value = _num(_ld_rating(html, "Metascore").get("ratingValue"))
    if value is None or not 0 <= value <= 100:
        return None
    return Link(url=url, score=f"{value:.0f}", score_value=value)


def goodreads(f: Fetcher, book_id: str) -> Link | None:
    """Average reader rating out of 5. book_id as Wikidata P2969 gives it ("42036538")."""
    clean = _path(book_id)
    if clean is None or "/" in clean:
        return None
    url = f"https://www.goodreads.com/book/show/{clean}"
    html = f.get_text(url, headers=HTML)
    if html is None:
        return None
    value = _num(_ld_rating(html).get("ratingValue"))
    if value is None or not 0 < value <= 5:  # an unrated book carries 0
        return None
    return Link(url=url, score=f"{value:.2f}", score_value=value)


# Page JSON ------------------------------------------------------------------------------------------


def _scripts(html: str) -> Iterator[tuple[dict[str, str], str]]:
    for m in _SCRIPT.finditer(html):
        attrs = {a.group(1).lower(): next(v for v in a.groups()[1:] if v is not None) for a in _ATTR.finditer(m.group(1))}
        yield attrs, m.group(2)


def _block(html: str, id_: str) -> Any:
    """Parsed body of <script id="..." type="application/json">, or None."""
    for attrs, body in _scripts(html):
        if attrs.get("id") == id_:
            return _loads(body)
    return None


def _ld_rating(html: str, name: str | None = None) -> dict[str, Any]:
    """The first schema.org aggregateRating in the page's JSON-LD; with `name`, one so named (or unnamed)."""
    for attrs, body in _scripts(html):
        if attrs.get("type", "").lower() != "application/ld+json":
            continue
        for node in _ld_nodes(_loads(body)):
            r = node.get("aggregateRating")
            if isinstance(r, dict) and (name is None or r.get("name", name) == name):
                return r
    return {}


def _ld_nodes(doc: Any) -> Iterator[dict[str, Any]]:
    if isinstance(doc, list):
        for d in doc:
            yield from _ld_nodes(d)
    elif isinstance(doc, dict):
        yield doc
        yield from _ld_nodes(doc.get("@graph"))


def _loads(body: str) -> Any:
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _path(path: str) -> str | None:
    """A site path from an id, or None when it is not a plain path (no queries, no "..", no search pages)."""
    parts = (path or "").strip().strip("/").split("/")
    if not all(_SEGMENT.fullmatch(p) and p not in (".", "..") for p in parts) or parts[0].lower() == "search":
        return None
    return "/".join(parts)
