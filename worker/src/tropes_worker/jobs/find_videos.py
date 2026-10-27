"""find_videos: openings, endings and title sequences for the works, with no model (ROADMAP backlog, 2026-10-27).

Sources, in the owner's order: AnimeThemes (every OP and ED of an anime, by MyAnimeList or AniDB id, else by
name and year), Art of the Title (title sequences, by the article's slug, checked against the title and year),
TMDB (videos typed "Opening Credits", or clips named like one; trailers are left alone). Payload
{mediaIds?, auto, sources?}. Rows go to POST /api/videos; the owner's own rows are never overwritten.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..lookup.http import Fetcher
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.find_videos")

ANIMETHEMES = "https://api.animethemes.moe"
THEME_INCLUDE = "animethemes.animethemeentries.videos,animethemes.song.artists,resources"
AOTT = "https://www.artofthetitle.com"
TMDB = "https://api.themoviedb.org/3"
OPENING_RX = re.compile(r"\b(opening (credits|titles?|sequence)|title sequence|main titles?|title credits|intro)\b", re.I)
NOT_OPENING_RX = re.compile(r"trailer|teaser|promo|scene|recap", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def is_anime(m: dict[str, Any]) -> bool:
    ids = m.get("externalIds") or {}
    if ids.get("mal") or ids.get("anidb") or ids.get("ann"):
        return True
    if any(g.lower() == "anime" for g in m.get("genres") or []):
        return True
    return any(str(s.get("path") or "").startswith("Anime/") for s in m.get("localSources") or [])


def work_year(m: dict[str, Any]) -> int | None:
    start = str((m.get("details") or {}).get("start") or "")
    return int(start[:4]) if start[:4].isdigit() else None


# AnimeThemes ---------------------------------------------------------------------------------


def pick_video(videos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The version to embed: no overlap with the episode, the aired version with credits over creditless, then
    the sharpest, then Blu-ray over web."""
    if not videos:
        return None
    return sorted(
        videos,
        key=lambda v: (
            (v.get("overlap") or "None") != "None",
            bool(v.get("nc")),
            -int(v.get("resolution") or 0),
            (v.get("source") or "") != "BD",
        ),
    )[0]


def theme_rows(anime: dict[str, Any], media_id: int) -> list[dict[str, Any]]:
    """One row per OP and ED of an AnimeThemes anime record."""
    rows = []
    for t in anime.get("animethemes") or []:
        kind = {"OP": "opening", "ED": "ending"}.get(t.get("type") or "")
        if not kind:
            continue
        seq = t.get("sequence") or 1
        song = t.get("song") or {}
        artists = ", ".join(a.get("name", "") for a in song.get("artists") or [] if a.get("name"))
        label = f"{t.get('type')}{seq}"
        if song.get("title"):
            label += f" · {song['title']}" + (f" — {artists}" if artists else "")
        video = pick_video([v for e in t.get("animethemeentries") or [] for v in e.get("videos") or []])
        if not video or not video.get("link"):
            continue
        rows.append(
            {
                "mediaId": media_id,
                "kind": kind,
                "url": video["link"],
                "label": label,
                "origin": "animethemes",
                "sourceUrl": f"https://animethemes.moe/anime/{anime.get('slug')}/{t.get('slug')}"
                if anime.get("slug") and t.get("slug")
                else None,
                "position": (0 if kind == "opening" else 100) + int(seq),
            }
        )
    return rows


def animethemes_anime(f: Fetcher, m: dict[str, Any]) -> dict[str, Any] | None:
    ids = m.get("externalIds") or {}
    for site, key in (("MyAnimeList", "mal"), ("aniDB", "anidb")):
        if not ids.get(key):
            continue
        d = f.get_json(
            f"{ANIMETHEMES}/anime",
            {
                "filter[has]": "resources",
                "filter[resource][site]": site,
                "filter[resource][external_id]": str(ids[key]),
                "include": THEME_INCLUDE,
            },
        )
        found = (d or {}).get("anime") or []
        if found:
            return found[0]
    # By name: the record whose name (or synonym) is the title and whose year is the work's, within a year.
    d = f.get_json(
        f"{ANIMETHEMES}/search",
        {"q": m["title"], "fields[search]": "anime", "include[anime]": THEME_INCLUDE + ",animesynonyms", "page[limit]": 8},
    )
    year = work_year(m)
    want = norm(m["title"])
    for a in ((d or {}).get("search") or {}).get("anime") or []:
        names = [a.get("name") or ""] + [s.get("text") or "" for s in a.get("animesynonyms") or []]
        if want not in {norm(n) for n in names}:
            continue
        if year and a.get("year") and abs(int(a["year"]) - year) > 1:
            continue
        return a
    return None


# Art of the Title -------------------------------------------------------------------------------


def aott_slugs(title: str, year: int | None) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    out = [base]
    if year:
        out.append(f"{base}-{year}")
    if base.startswith("the-"):
        out.append(base[4:])
    return [s for s in dict.fromkeys(out) if s]


def aott_page(f: Fetcher, title: str, year: int | None) -> tuple[str, str] | None:
    """(article url, vimeo id) when Art of the Title has the title sequence, checked by name and year."""
    for slug in aott_slugs(title, year):
        url = f"{AOTT}/title/{slug}/"
        html = f.get_text(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TropeLog/0.1)"})
        if not html:
            continue
        m = re.search(r"<title>(.*?)\s*\((\d{4})\)\s*&mdash;", html, re.S)
        if not m or norm(m.group(1)) != norm(title):
            continue
        if year and abs(int(m.group(2)) - year) > 1:
            continue
        # The first embed on the article is the title sequence itself; later ones are related sequences and trailers.
        vimeo = re.findall(r'data-vimeoid="(\d+)"', html) or re.findall(r"player\.vimeo\.com/video/(\d+)", html)
        if vimeo:
            return url, vimeo[0]
    return None


# TMDB ----------------------------------------------------------------------------------------------


def tmdb_titles(videos: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(youtube key, label) for videos that are the opening credits or a clip named like a title sequence."""
    out = []
    for v in videos:
        if v.get("site") != "YouTube" or not v.get("key"):
            continue
        name = v.get("name") or ""
        if v.get("type") == "Opening Credits" or (
            v.get("type") in ("Clip", "Featurette") and OPENING_RX.search(name) and not NOT_OPENING_RX.search(name)
        ):
            out.append((v["key"], name if name and name.lower() != "opening credits" else "Opening credits"))
    return out


def tmdb_rows(f: Fetcher, token: str, m: dict[str, Any]) -> list[dict[str, Any]]:
    ids = m.get("externalIds") or {}
    headers = {"Authorization": f"Bearer {token}"}
    paths = []
    if ids.get("tmdb_tv"):
        paths += [f"tv/{ids['tmdb_tv']}/videos", f"tv/{ids['tmdb_tv']}/season/1/videos"]
    if ids.get("tmdb_movie"):
        paths.append(f"movie/{ids['tmdb_movie']}/videos")
    rows = []
    seen: set[str] = set()
    for p in paths:
        d = f.get_json(f"{TMDB}/{p}", headers=headers)
        for key, label in tmdb_titles((d or {}).get("results") or []):
            if key in seen:
                continue
            seen.add(key)
            kind = "ending" if re.search(r"\bend(ing)? (credits|titles?)\b", label, re.I) else "titles"
            rows.append(
                {
                    "mediaId": m["id"],
                    "kind": kind,
                    "url": f"https://www.youtube.com/watch?v={key}",
                    "label": label,
                    "origin": "tmdb",
                    "position": 0,
                }
            )
    return rows


# The job -------------------------------------------------------------------------------------------


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    wanted = set(payload.get("mediaIds") or [])
    sources = set(payload.get("sources") or ["animethemes", "artofthetitle", "tmdb"])
    media = [
        m for m in ctx.client.subjects()["media"] if m.get("type") in ("TV Series", "Movie") and (not wanted or m["id"] in wanted)
    ]
    f = Fetcher(cache_dir=settings.lookup_cache_dir, user_agent=settings.user_agent, max_age_days=7)
    counts = {"works": len(media), "anime": 0, "animethemes": 0, "artofthetitle": 0, "tmdb": 0, "posted": 0}
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        ctx.progress(0, len(media), "videos")
        for n, m in enumerate(media, 1):
            year = work_year(m)
            if is_anime(m):
                counts["anime"] += 1
                if "animethemes" in sources:
                    a = animethemes_anime(f, m)
                    if a:
                        found = theme_rows(a, m["id"])
                        rows += found
                        counts["animethemes"] += len(found)
                    else:
                        warnings.append(f"not on AnimeThemes: {m['title']}")
            if "artofthetitle" in sources:
                hit = aott_page(f, m["title"], year)
                if hit:
                    page, vimeo = hit
                    rows.append(
                        {
                            "mediaId": m["id"],
                            "kind": "titles",
                            "url": f"https://vimeo.com/{vimeo}",
                            "label": "Title sequence",
                            "origin": "artofthetitle",
                            "sourceUrl": page,
                            "position": 0,
                        }
                    )
                    counts["artofthetitle"] += 1
            if "tmdb" in sources and settings.tmdb_token and not is_anime(m):
                found = tmdb_rows(f, settings.tmdb_token, m)
                rows += found
                counts["tmdb"] += len(found)
            if n % 20 == 0:
                ctx.progress(n, len(media), "videos")
                if rows:
                    counts["posted"] += len(rows)
                    ctx.client.post_videos(rows)
                    rows = []
        if rows:
            counts["posted"] += len(rows)
            ctx.client.post_videos(rows)
        ctx.progress(len(media), len(media), "done")
    finally:
        f.close()
    return {"summary": {**counts, "requests": f.requests_made}, "warnings": (warnings + f.warnings)[:60]}
