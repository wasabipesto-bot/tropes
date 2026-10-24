"""MyAnimeList v2 (official API): anime details and search."""

from __future__ import annotations

from .http import Fetcher
from .models import Candidate, Link, Partial

BASE = "https://api.myanimelist.net/v2"
FETCH_FIELDS = (
    "id,title,main_picture,alternative_titles,start_date,end_date,mean,num_episodes,media_type,status,genres,studios,"
    "source,start_season"
)
SEARCH_FIELDS = "id,title,start_date,media_type,alternative_titles,mean,synopsis"
TV_MEDIA_TYPES = {"tv", "ona", "ova", "special"}


def _headers(settings) -> dict[str, str]:
    return {"X-MAL-CLIENT-ID": settings.mal_client_id}


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    if not settings.mal_client_id:
        return Partial(warnings=["MAL: no TROPES_MAL_CLIENT_ID, skipped"])
    mal_id = ids.get("mal")
    if not mal_id:
        return None
    d = f.get_json(f"{BASE}/anime/{mal_id}", params={"fields": FETCH_FIELDS}, headers=_headers(settings))
    if not d:
        return None
    details: dict = {}
    if d.get("start_date"):
        details["start"] = d["start_date"]
    if d.get("end_date"):
        details["end"] = d["end_date"]
    if d.get("num_episodes"):
        details["episodes"] = d["num_episodes"]
    studios = [s["name"] for s in d.get("studios") or [] if s.get("name")]
    if studios:
        details["studio"] = ", ".join(studios)
    if d.get("source"):
        details["source_material"] = d["source"]
    if d.get("status"):
        details["status"] = d["status"]
    genres = [g["name"] for g in d.get("genres") or [] if g.get("name")]
    picture = d.get("main_picture") or {}
    poster = picture.get("large") or picture.get("medium")
    mean = d.get("mean")
    score = f"{mean:.2f}" if mean is not None else None
    link = Link(url=f"https://myanimelist.net/anime/{mal_id}", score=score, score_value=mean)
    return Partial(details=details, genres=genres, posters=[poster] if poster else [], links={"mal": link})


def search(f: Fetcher, title: str, year: int | None, *, type_: str, settings) -> list[Candidate]:
    if not settings.mal_client_id:
        return []
    d = f.get_json(f"{BASE}/anime", params={"q": title, "limit": 10, "fields": SEARCH_FIELDS}, headers=_headers(settings))
    if not d:
        return []
    out: list[Candidate] = []
    for entry in d.get("data") or []:
        node = entry.get("node") or {}
        media_type = node.get("media_type")
        if type_ == "TV Series" and media_type not in TV_MEDIA_TYPES:
            continue
        if type_ == "Movie" and media_type != "movie":
            continue
        kind = "anime film" if media_type == "movie" else "anime television series"
        out.append(
            Candidate(
                qid=None,
                label=node.get("title", ""),
                description=(node.get("synopsis") or "")[:160],
                year=_year(node.get("start_date")),
                ids={"mal": str(node["id"])},
                source="mal",
                kinds=[kind],
            )
        )
    return out
