"""TMDB v3: TV and movie details, external ids, posters and genres."""

from __future__ import annotations

from .http import Fetcher
from .models import Candidate, Link, Partial

BASE = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/original"


def _headers(settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.tmdb_token}"}


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def _genres(d: dict) -> list[str]:
    return [g["name"] for g in d.get("genres") or [] if g.get("name")]


def _posters(d: dict, poster_path: str | None) -> list[str]:
    """Main poster first, then up to 12 more by vote_count, skipping a duplicate of the main one."""
    out = [f"{IMG_BASE}{poster_path}"] if poster_path else []
    extras = sorted(d.get("images", {}).get("posters") or [], key=lambda p: p.get("vote_count", 0), reverse=True)
    added = 0
    for p in extras:
        fp = p.get("file_path")
        if not fp or fp == poster_path:
            continue
        out.append(f"{IMG_BASE}{fp}")
        added += 1
        if added >= 12:
            break
    return out


def _resolve_id(f: Fetcher, imdb_id: str, type_: str, settings) -> tuple[str, str] | None:
    """(kind, tmdb id) for an IMDb id via /find; kind is "tv" or "movie"."""
    d = f.get_json(f"{BASE}/find/{imdb_id}", params={"external_source": "imdb_id"}, headers=_headers(settings))
    if not d:
        return None
    tv_hits, movie_hits = d.get("tv_results") or [], d.get("movie_results") or []
    if type_ == "TV Series":
        return ("tv", str(tv_hits[0]["id"])) if tv_hits else None
    if type_ == "Movie":
        return ("movie", str(movie_hits[0]["id"])) if movie_hits else None
    if tv_hits:
        return ("tv", str(tv_hits[0]["id"]))
    if movie_hits:
        return ("movie", str(movie_hits[0]["id"]))
    return None


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    if not settings.tmdb_token:
        return Partial(warnings=["TMDB: no TROPES_TMDB_TOKEN, skipped"])
    tv_id, movie_id = ids.get("tmdb_tv"), ids.get("tmdb_movie")
    discovered: dict[str, str] = {}
    if not tv_id and not movie_id and ids.get("imdb"):
        hit = _resolve_id(f, ids["imdb"], type_, settings)
        if hit is None:
            return None
        kind, hid = hit
        if kind == "tv":
            tv_id = hid
            discovered["tmdb_tv"] = hid
        else:
            movie_id = hid
            discovered["tmdb_movie"] = hid
    if tv_id:
        return _fetch_tv(f, tv_id, settings, discovered)
    if movie_id:
        return _fetch_movie(f, movie_id, settings, discovered)
    return None


def _fetch_tv(f: Fetcher, tmdb_id: str, settings, discovered: dict[str, str]) -> Partial | None:
    d = f.get_json(
        f"{BASE}/tv/{tmdb_id}",
        params={"append_to_response": "external_ids,images", "include_image_language": "en,null"},
        headers=_headers(settings),
    )
    if not d:
        return None
    details: dict = {}
    if d.get("first_air_date"):
        details["start"] = d["first_air_date"]
    if d.get("last_air_date"):
        details["end"] = d["last_air_date"]
    if d.get("number_of_seasons") is not None:
        details["seasons"] = d["number_of_seasons"]
    if d.get("number_of_episodes") is not None:
        details["episodes"] = d["number_of_episodes"]
    networks = d.get("networks") or []
    if networks and networks[0].get("name"):
        details["network"] = networks[0]["name"]
    if d.get("status"):
        details["status"] = d["status"]
    ext = d.get("external_ids") or {}
    ids_out = dict(discovered)
    if ext.get("imdb_id"):
        ids_out["imdb"] = ext["imdb_id"]
    if ext.get("tvdb_id"):
        ids_out["tvdb"] = str(ext["tvdb_id"])
    return Partial(
        details=details,
        genres=_genres(d),
        posters=_posters(d, d.get("poster_path")),
        ids=ids_out,
        links={"tmdb": Link(url=f"https://www.themoviedb.org/tv/{tmdb_id}")},
    )


def _fetch_movie(f: Fetcher, tmdb_id: str, settings, discovered: dict[str, str]) -> Partial | None:
    d = f.get_json(
        f"{BASE}/movie/{tmdb_id}",
        params={"append_to_response": "external_ids,images,credits", "include_image_language": "en,null"},
        headers=_headers(settings),
    )
    if not d:
        return None
    details: dict = {}
    if d.get("release_date"):
        details["start"] = d["release_date"]
    if d.get("runtime"):
        details["runtime_min"] = d["runtime"]
    companies = d.get("production_companies") or []
    if companies and companies[0].get("name"):
        details["studio"] = companies[0]["name"]
    crew = (d.get("credits") or {}).get("crew") or []
    directors = [c["name"] for c in crew if c.get("job") == "Director" and c.get("name")]
    if directors:
        details["director"] = ", ".join(directors)
    ext = d.get("external_ids") or {}
    ids_out = dict(discovered)
    if ext.get("imdb_id"):
        ids_out["imdb"] = ext["imdb_id"]
    return Partial(
        details=details,
        genres=_genres(d),
        posters=_posters(d, d.get("poster_path")),
        ids=ids_out,
        links={"tmdb": Link(url=f"https://www.themoviedb.org/movie/{tmdb_id}")},
    )


def search(f: Fetcher, title: str, year: int | None, *, type_: str, settings) -> list[Candidate]:
    if not settings.tmdb_token:
        return []
    headers = _headers(settings)
    out: list[Candidate] = []
    if type_ != "Movie":
        d = f.get_json(f"{BASE}/search/tv", params={"query": title}, headers=headers)
        for r in (d.get("results") or [])[:10] if d else []:
            out.append(
                Candidate(
                    qid=None,
                    label=r.get("name", ""),
                    description=(r.get("overview") or "")[:160],
                    year=_year(r.get("first_air_date")),
                    ids={"tmdb_tv": str(r["id"])},
                    source="tmdb",
                    kinds=["television series"],
                )
            )
    if type_ != "TV Series":
        d = f.get_json(f"{BASE}/search/movie", params={"query": title}, headers=headers)
        for r in (d.get("results") or [])[:10] if d else []:
            out.append(
                Candidate(
                    qid=None,
                    label=r.get("title", ""),
                    description=(r.get("overview") or "")[:160],
                    year=_year(r.get("release_date")),
                    ids={"tmdb_movie": str(r["id"])},
                    source="tmdb",
                    kinds=["film"],
                )
            )
    return out
