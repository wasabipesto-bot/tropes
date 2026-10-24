"""lookup_media: resolve each work's identity, fetch its details, scores, poster and genres, and propose the match.

Payload {mediaIds, auto, refresh}. A refresh re-fetches from the pinned identity and never re-matches (plan D1).
Nothing is written on the site until the match is committed: posters go to the pending directory, and the
result is one `match` proposal per work carrying everything the commit needs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..llm import LLM
from ..lookup import imdb, itunes, mal, musicbrainz, openlibrary, scores, steam, tmdb, wikidata, wikipedia
from ..lookup.genres import assign
from ..lookup.http import Fetcher
from ..lookup.merge import merge
from ..lookup.models import Candidate, Partial
from ..lookup.posters import prepare
from ..lookup.report import entry_from, shared_media_links
from ..lookup.resolve import Entry, Resolution, norm, resolve
from ..pipeline import entry_text, run_async
from ..runner import Context
from ..schemas import ResolveOut

log = logging.getLogger("tropes_worker.jobs.lookup_media")
WORKERS = 6


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


def pinned(m: dict[str, Any]) -> Resolution:
    c = Candidate(
        qid=m.get("wikidataId"),
        label=m["title"],
        ids=dict(m.get("externalIds") or {}),
        score=1.0,
        reasons=["pinned"],
        source="pinned",
    )
    return Resolution("confident", c, [], None, ["refresh of the pinned identity"])


def site_search(f: Fetcher, settings: Any, entry: Entry) -> Candidate | None:
    """Per-site fallback when Wikidata has nothing: the top hit, only when its title is the title."""
    t = entry.type
    hits: list[Candidate] = []
    try:
        if t in ("TV Series", "Movie"):
            hits = tmdb.search(f, entry.title, entry.logged_year, type_=t, settings=settings)
        elif t == "Game":
            hits = steam.search(f, entry.title, entry.creator, entry.logged_year, type_=t, settings=settings)
        elif t in ("Book", "Other"):
            hits = openlibrary.search(f, entry.title, entry.creator, entry.logged_year, type_=t, settings=settings)
        elif t == "Album":
            hits = musicbrainz.search(f, entry.title, entry.creator, entry.logged_year, type_=t, settings=settings)
        elif t == "Podcast":
            hits = itunes.search(f, entry.title, entry.creator, entry.logged_year, type_=t, settings=settings)
    except Exception as e:  # noqa: BLE001 - a fallback search must never fail the job
        f.warn(f"site search for {entry.title!r}: {type(e).__name__}")
    for c in hits:
        if norm(c.label) == norm(entry.title) and (not entry.logged_year or not c.year or c.year <= entry.logged_year):
            c.score, c.reasons = 0.6, ["title matches on the site", "not in Wikidata"]
            return c
    return None


def gather_partials(
    f: Fetcher, settings: Any, type_: str, chosen: Candidate, ratings: dict[str, tuple[float, int]]
) -> dict[str, Partial]:
    parts: dict[str, Partial] = {}
    ids = dict(chosen.ids)
    if chosen.qid:
        ent = wikidata.entities(f, [chosen.qid]).get(chosen.qid)
        if ent:
            names = wikidata.labels(f, wikidata.linked_qids(ent))
            parts["wikidata"] = wikidata.partial(ent, names, type_)
            ids = {**parts["wikidata"].ids, **ids}
    if chosen.wikipedia:
        w = wikipedia.summary(f, chosen.wikipedia)
        if w:
            parts["wikipedia"] = w

    def add(name: str, p: Partial | None) -> None:
        if p is not None:
            parts[name] = p
            ids.update({k: v for k, v in p.ids.items() if k not in ids})

    if type_ in ("TV Series", "Movie") or "tmdb_tv" in ids or "tmdb_movie" in ids:
        add("tmdb", tmdb.fetch(f, ids, type_=type_, settings=settings))
    if "mal" in ids:
        add("mal", mal.fetch(f, ids, type_=type_, settings=settings))
    if "steam" in ids:
        add("steam", steam.fetch(f, ids, type_=type_, settings=settings))
    if "openlibrary" in ids and type_ in ("Book", "Other"):
        add("openlibrary", openlibrary.fetch(f, ids, type_=type_, settings=settings))
    if "musicbrainz_rg" in ids:
        add("musicbrainz", musicbrainz.fetch(f, ids, type_=type_, settings=settings))
    if "itunes" in ids or "itunes_album" in ids:
        add("itunes", itunes.fetch(f, {"itunes": ids.get("itunes") or ids["itunes_album"]}, type_=type_, settings=settings))
    if "imdb" in ids:
        add("imdb", imdb.fetch(f, ids, type_=type_, settings=settings, ratings=ratings))
    sc = Partial()
    if "rt" in ids and type_ in ("TV Series", "Movie"):
        link = scores.rotten_tomatoes(f, ids["rt"])
        if link:
            sc.links["rt"] = link
    if "metacritic" in ids and type_ in ("TV Series", "Movie", "Game"):
        link = scores.metacritic(f, ids["metacritic"])
        if link:
            sc.links["metacritic"] = link
    if "goodreads" in ids and type_ in ("Book", "Other"):
        link = scores.goodreads(f, ids["goodreads"])
        if link:
            sc.links["goodreads"] = link
    if sc.links:
        parts["scores"] = sc
    for p in parts.values():
        for key, value in p.ids.items():
            ids.setdefault(key, value)
    merged_ids = Partial(ids=ids)
    parts["_ids"] = merged_ids
    return parts


def candidate_lines(cands: list[Candidate]) -> str:
    lines = []
    for c in cands:
        kind = ", ".join(c.kinds) or "?"
        desc = c.description or "(no description)"
        lines.append(f"- id {c.qid}: {c.label} — {desc}; year {c.year or '?'}; creator {c.creator or '?'}; kind {kind}")
    return "\n".join(lines)


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    client = ctx.client
    wanted = set(payload["mediaIds"])
    refresh = bool(payload.get("refresh"))
    all_media = client.subjects()["media"]
    rows = [m for m in all_media if m["id"] in wanted]
    shared = shared_media_links(all_media)
    vocab = client.genres()
    f = Fetcher(cache_dir=settings.lookup_cache_dir, user_agent=settings.user_agent)
    llm = LLM(settings)
    started = time.monotonic()
    total = len(rows) * 3 + 1
    done = 0
    loop = asyncio.get_running_loop()
    pool = ThreadPoolExecutor(max_workers=WORKERS)

    async def in_thread(fn, *args):  # noqa: ANN001, ANN202
        return await loop.run_in_executor(pool, fn, *args)

    ctx.progress(0, total, "resolving")

    # A. Identity.
    async def resolve_one(m: dict[str, Any]) -> tuple[dict[str, Any], Resolution]:
        nonlocal done
        if refresh and m.get("identity") == "pinned" and (m.get("wikidataId") or m.get("externalIds")):
            r = pinned(m)
        else:
            r = await in_thread(lambda: resolve(f, entry_from(m), shared_links=shared))
        done += 1
        ctx.progress(done, total, "resolving")
        return m, r

    resolved = await asyncio.gather(*(resolve_one(m) for m in rows))

    # B. The model breaks ties; per-site search covers what Wikidata lacks.
    async def settle(m: dict[str, Any], r: Resolution) -> tuple[dict[str, Any], Resolution]:
        if r.status == "check" and len(r.candidates) > 1 and r.chosen and r.chosen.source != "seed":
            try:
                out = await llm.complete(
                    "resolve", {"entry": entry_text(m), "candidates": candidate_lines(r.candidates)}, ResolveOut
                )
            except Exception as e:  # noqa: BLE001 - the deterministic answer stands when the model fails
                r.notes.append(f"tiebreak failed: {type(e).__name__}")
                return m, r
            pick = next((c for c in r.candidates if c.qid == out.choice), None)
            if pick is None:
                r.status, r.chosen = "not_found", None
                r.notes.append(f"model: none of the candidates ({out.why})")
            else:
                r.chosen = pick
                r.candidates.sort(key=lambda c: c is not pick)
                r.status = "confident" if out.confidence >= 0.8 else "check"
                r.notes.append(f"model chose it ({out.confidence:.2f}): {out.why}")
        if r.status == "not_found":
            c = await in_thread(site_search, f, settings, entry_from(m))
            if c:
                r.status, r.chosen = "check", c
                r.candidates = [c] + [x for x in r.candidates if x is not c][:4]
        return m, r

    settled = await asyncio.gather(*(settle(m, r) for m, r in resolved))

    # C. Details, links, scores and posters for everything with an identity.
    imdb_ids = {r.chosen.ids["imdb"] for _, r in settled if r.chosen and "imdb" in r.chosen.ids}
    ratings = await in_thread(lambda: imdb.ratings_for(f, settings, imdb_ids)) if imdb_ids else {}

    def fetch_one(m: dict[str, Any], r: Resolution) -> tuple[Partial | None, dict[str, Any] | None]:
        if not r.chosen:
            return None, None
        parts = gather_partials(f, settings, m["type"], r.chosen, ratings)
        ids = parts.pop("_ids").ids
        merged = merge(m["type"], parts)
        merged.ids = ids
        poster_info = None
        urls = ([m["imageUrl"]] if m.get("imageUrl") else []) + merged.posters
        keep = refresh and m.get("posterPath") and urls and m.get("posterSource") == urls[0]
        if urls and not keep:
            got = prepare(f, urls)
            if got:
                source, files = got
                client.upload_poster(m["id"], source, files, pending=True)
                poster_info = {"source": source}
        return merged, poster_info

    async def fetch_wrapped(
        m: dict[str, Any], r: Resolution
    ) -> tuple[dict[str, Any], Resolution, Partial | None, dict[str, Any] | None]:
        nonlocal done
        try:
            merged, poster = await in_thread(fetch_one, m, r)
        except Exception as e:  # noqa: BLE001 - one work's fetch must not fail the batch
            log.warning("fetch failed for %s: %s", m["title"], e)
            f.warn(f"{m['title']}: fetch failed ({type(e).__name__})")
            merged, poster = None, None
        done += 1
        ctx.progress(done, total, "fetching")
        return m, r, merged, poster

    fetched = await asyncio.gather(*(fetch_wrapped(m, r) for m, r in settled))

    # D. Genres from the vocabulary.
    async def genres_for(m: dict[str, Any], merged: Partial | None) -> list[str]:
        nonlocal done
        out: list[str] = []
        if merged is not None and not m.get("genresEdited"):
            try:
                out = await assign(llm, vocab, entry_text(m), m["type"], merged.genres, merged.extract)
            except Exception as e:  # noqa: BLE001
                f.warn(f"{m['title']}: genres failed ({type(e).__name__})")
        done += 1
        ctx.progress(done, total, "genres")
        return out

    genres = await asyncio.gather(*(genres_for(m, merged) for m, _, merged, _ in fetched))
    pool.shutdown(wait=False)
    f.close()

    proposals = []
    counts = {"confident": 0, "check": 0, "not_found": 0}
    for (m, r, merged, poster), g in zip(fetched, genres, strict=True):
        counts[r.status] = counts.get(r.status, 0) + 1
        c = r.chosen
        text = (
            f"{c.label}: {c.description or ', '.join(c.kinds) or 'no description'}" + (f", {c.year}" if c and c.year else "")
            if c
            else "No match found"
        )
        proposals.append(
            {
                "subject": {"kind": "media", "id": m["id"]},
                "kind": "match",
                "score": min(1.0, max(0.0, c.score)) if c else 0.0,
                "who": "",
                "text": text,
                "evidence": [],
                "flags": [],
                "payload": {
                    "status": r.status,
                    "chosen": c.as_dict() if c else None,
                    "candidates": [x.as_dict() for x in r.candidates[:5]],
                    "details": merged.details if merged else {},
                    "links": {
                        k: {"url": v.url, "score": v.score, "score_value": v.score_value}
                        for k, v in (merged.links if merged else {}).items()
                    },
                    "genres": g,
                    "ids": merged.ids if merged else (c.ids if c else {}),
                    "extract": merged.extract if merged else None,
                    "poster": poster,
                    "notes": r.notes + (merged.warnings if merged else []),
                },
            }
        )
    ctx.progress(total, total, "done")
    summary = {
        **counts,
        "looked_up": len(rows),
        "refresh": refresh,
        "requests": f.requests_made,
        "cacheHits": f.cache_hits,
        "seconds": round(time.monotonic() - started),
    }
    return {"summary": summary, "proposals": proposals, "usage": llm.usage.as_dict(), "warnings": f.warnings[:40]}
