"""MusicBrainz release-group API for fetch, plus the Cover Art Archive for posters. No key needed;
the Fetcher's User-Agent satisfies MusicBrainz's request for one."""

from __future__ import annotations

from .http import Fetcher
from .models import Candidate, Link, Partial


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    mbid = ids.get("musicbrainz_rg")
    if not mbid:
        return None
    params = {"inc": "artist-credits+tags+releases", "fmt": "json"}
    rg = f.get_json(f"https://musicbrainz.org/ws/2/release-group/{mbid}", params=params)
    if not rg:
        return None

    details: dict[str, object] = {}
    start = rg.get("first-release-date")
    if start:
        details["start"] = start

    artist = _credit_phrase(rg.get("artist-credit") or [])
    if artist:
        details["artist"] = artist

    officials = [r for r in rg.get("releases") or [] if r.get("status") == "Official" and r.get("id")]
    if officials:
        first = min(officials, key=lambda r: r.get("date") or "9999-99-99")
        release = f.get_json(f"https://musicbrainz.org/ws/2/release/{first['id']}", params={"inc": "media", "fmt": "json"})
        if release:
            tracks = sum(m.get("track-count") or 0 for m in release.get("media") or [])
            if tracks:
                details["tracks"] = tracks

    tags = sorted((t for t in rg.get("tags") or [] if t.get("count", 0) >= 1), key=lambda t: -t["count"])
    genres = [t["name"] for t in tags[:10]]

    posters = []
    cover_url = f"https://coverartarchive.org/release-group/{mbid}/front-500"
    if f.status(cover_url) == 200:
        posters.append(cover_url)

    links = {"musicbrainz": Link(url=f"https://musicbrainz.org/release-group/{mbid}")}

    return Partial(details=details, links=links, posters=posters, genres=genres, ids={"musicbrainz_rg": mbid})


def search(f: Fetcher, title: str, creator: str | None, year: int | None, *, type_: str, settings) -> list[Candidate]:
    query = f'releasegroup:"{title}"'
    if creator:
        query += f' AND artist:"{creator}"'
    data = f.get_json("https://musicbrainz.org/ws/2/release-group", params={"query": query, "fmt": "json", "limit": 10})
    if not data:
        return []
    out = []
    for rg in (data.get("release-groups") or [])[:10]:
        if not rg.get("id") or not rg.get("title"):
            continue
        year_ = None
        frd = rg.get("first-release-date") or ""
        if len(frd) >= 4 and frd[:4].isdigit():
            year_ = int(frd[:4])
        out.append(
            Candidate(
                qid=None,
                label=rg["title"],
                ids={"musicbrainz_rg": rg["id"]},
                creator=_credit_phrase(rg.get("artist-credit") or []) or None,
                year=year_,
                kinds=["album"],
                source="musicbrainz",
            )
        )
    return out


def _credit_phrase(artist_credit: list[dict]) -> str:
    return "".join((a.get("name") or "") + (a.get("joinphrase") or "") for a in artist_credit)
