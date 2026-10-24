"""iTunes/Apple lookup and search APIs, for podcasts and albums. No key needed."""

from __future__ import annotations

from .http import Fetcher
from .models import Candidate, Link, Partial


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    tid = ids.get("itunes")
    if not tid:
        return None
    data = f.get_json("https://itunes.apple.com/lookup", params={"id": tid})
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]

    details: dict[str, object] = {}
    posters: list[str] = []
    genres: list[str] = []
    links: dict[str, Link] = {}

    if r.get("kind") == "podcast":
        episodes = r.get("trackCount")
        if episodes:
            details["episodes"] = episodes
        if r.get("artistName"):
            details["network"] = r["artistName"]
        genres = list(r.get("genres") or [])
        art = r.get("artworkUrl600")
        if art:
            posters.append(art.replace("600x600", "1200x1200"))
            posters.append(art)
        if r.get("collectionViewUrl"):
            links["itunes"] = Link(url=r["collectionViewUrl"])
    elif r.get("wrapperType") == "collection" and r.get("collectionType") == "Album":
        release = r.get("releaseDate")
        if release:
            details["start"] = release[:10]
        if r.get("artistName"):
            details["artist"] = r["artistName"]
        tracks = r.get("trackCount")
        if tracks:
            details["tracks"] = tracks
        if r.get("primaryGenreName"):
            genres = [r["primaryGenreName"]]
        art = r.get("artworkUrl100")
        if art:
            posters.append(art.replace("100x100", "1200x1200"))
        if r.get("collectionViewUrl"):
            links["itunes"] = Link(url=r["collectionViewUrl"])

    return Partial(details=details, links=links, posters=posters, genres=genres, ids={"itunes": str(tid)})


def search(f: Fetcher, title: str, creator: str | None, year: int | None, *, type_: str, settings) -> list[Candidate]:
    if type_ == "Podcast":
        params = {"term": title, "media": "podcast", "entity": "podcast", "limit": 10}
        kind = "podcast"
    elif type_ == "Album":
        params = {"term": title, "media": "music", "entity": "album", "limit": 10}
        kind = "album"
    else:
        return []
    data = f.get_json("https://itunes.apple.com/search", params=params)
    if not data:
        return []
    out = []
    for r in (data.get("results") or [])[:10]:
        cid = r.get("collectionId")
        name = r.get("collectionName")
        if cid is None or not name:
            continue
        year_ = None
        rd = r.get("releaseDate") or ""
        if len(rd) >= 4 and rd[:4].isdigit():
            year_ = int(rd[:4])
        out.append(
            Candidate(
                qid=None,
                label=name,
                ids={"itunes": str(cid)},
                creator=r.get("artistName"),
                year=year_,
                kinds=[kind],
                source="itunes",
            )
        )
    return out
