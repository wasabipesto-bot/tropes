"""Steam store API: appdetails for fetch, storesearch for search. No key needed."""

from __future__ import annotations

from datetime import datetime

from .http import Fetcher
from .models import Candidate, Link, Partial

_POSTER_BASE = "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{id}/{name}"


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    appid = ids.get("steam")
    if not appid:
        return None
    data = f.get_json("https://store.steampowered.com/api/appdetails", params={"appids": appid, "cc": "us", "l": "en"})
    if not data:
        return None
    entry = data.get(appid)
    if not entry or not entry.get("success"):
        return None
    app = entry.get("data") or {}

    details: dict[str, object] = {}
    date = _parse_release_date(((app.get("release_date") or {}).get("date")) or "")
    if date:
        details["start"] = date
    developers = app.get("developers") or []
    if developers:
        details["developer"] = ", ".join(developers)
    publishers = app.get("publishers") or []
    if publishers:
        details["publisher"] = ", ".join(publishers)
    platforms = [k for k, v in (app.get("platforms") or {}).items() if v]
    if platforms:
        details["platforms"] = platforms

    genres = [g["description"] for g in app.get("genres") or [] if g.get("description")]

    posters = []
    for name in ("library_600x900_2x.jpg", "library_600x900.jpg"):
        url = _POSTER_BASE.format(id=appid, name=name)
        if f.status(url) == 200:
            posters.append(url)
    header = app.get("header_image")
    if header and f.status(header) == 200:
        posters.append(header)

    links = {"steam": Link(url=f"https://store.steampowered.com/app/{appid}/")}
    metacritic = app.get("metacritic")
    if metacritic and metacritic.get("url"):
        links["metacritic"] = Link(url=metacritic["url"], score=str(metacritic.get("score")), score_value=metacritic.get("score"))

    return Partial(details=details, links=links, posters=posters, genres=genres, ids={"steam": str(appid)})


def search(f: Fetcher, title: str, creator: str | None, year: int | None, *, type_: str, settings) -> list[Candidate]:
    data = f.get_json("https://store.steampowered.com/api/storesearch/", params={"term": title, "l": "english", "cc": "US"})
    if not data:
        return []
    out = []
    for item in (data.get("items") or [])[:10]:
        if "id" not in item or not item.get("name"):
            continue
        out.append(Candidate(qid=None, label=item["name"], ids={"steam": str(item["id"])}, kinds=["video game"], source="steam"))
    return out


def _parse_release_date(raw: str) -> str | None:
    """Steam gives "3 Nov, 2019", "Nov 2019", "Aug 27, 2020" or a plain year, depending on locale."""
    s = raw.strip()
    if not s:
        return None
    for fmt in ("%b %d, %Y", "%d %b, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.strptime(s, "%b %Y").strftime("%Y-%m")
    except ValueError:
        pass
    if s.isdigit() and len(s) == 4:
        return s
    return None
