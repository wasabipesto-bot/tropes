"""Wikipedia's summary endpoint: the article URL, the lead paragraph and the lead image."""

from __future__ import annotations

from urllib.parse import quote

from .http import Fetcher
from .models import Link, Partial


def summary(f: Fetcher, title: str) -> Partial | None:
    d = f.get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}")
    if not d or d.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return None
    p = Partial()
    url = d.get("content_urls", {}).get("desktop", {}).get("page")
    if url:
        p.links["wikipedia"] = Link(url=url)
    extract = (d.get("extract") or "").strip()
    if extract:
        p.extract = extract
    image = d.get("originalimage", {}).get("source")
    if image:
        p.posters.append(image)
    if d.get("wikibase_item"):
        p.ids["wikidata"] = d["wikibase_item"]
    return p
