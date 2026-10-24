"""Combine per-site partials with a fixed precedence per type and field."""

from __future__ import annotations

from .models import Partial

# Source order per type; the first source that has a detail wins.
ORDER: dict[str, list[str]] = {
    "TV Series": ["tmdb", "mal", "wikidata", "wikipedia"],
    "Movie": ["tmdb", "mal", "wikidata", "wikipedia"],
    "Book": ["wikidata", "openlibrary", "wikipedia"],
    "Game": ["steam", "wikidata", "wikipedia"],
    "Album": ["musicbrainz", "wikidata", "itunes", "wikipedia"],
    "Podcast": ["itunes", "wikidata", "wikipedia"],
    "Other": ["wikidata", "openlibrary", "wikipedia"],
}
# Fields where a later source knows better: MAL over TMDB for anime counts and credits.
OVERRIDE: dict[str, dict[str, list[str]]] = {
    "TV Series": {"episodes": ["mal", "tmdb"], "studio": ["mal", "tmdb"], "source_material": ["mal"]},
    "Movie": {"studio": ["mal", "tmdb"]},
}
# Poster precedence (the Notion Image Link is handled by the job and always comes first).
POSTER_ORDER = ["tmdb", "steam", "mal", "openlibrary", "musicbrainz", "itunes", "wikipedia", "wikidata"]
# Links with a score from a dedicated reader replace the bare link Wikidata built from the id.
SCORED = ["imdb", "scores", "mal", "steam", "tmdb"]


def merge(type_: str, parts: dict[str, Partial]) -> Partial:
    out = Partial()
    order = ORDER.get(type_, ORDER["Other"]) + [s for s in parts if s not in ORDER.get(type_, ORDER["Other"])]
    for key in {k for p in parts.values() for k in p.details}:
        sources = OVERRIDE.get(type_, {}).get(key, []) + order
        for src in sources:
            p = parts.get(src)
            if p and key in p.details and p.details[key] not in (None, "", []):
                out.details[key] = p.details[key]
                break
    for src in order:
        p = parts.get(src)
        if not p:
            continue
        for site, link in p.links.items():
            if site not in out.links:
                out.links[site] = link
        for k, v in p.ids.items():
            out.ids.setdefault(k, v)
    for src in SCORED:
        p = parts.get(src)
        if p:
            for site, link in p.links.items():
                if link.score is not None or site not in out.links:
                    out.links[site] = link
    for src in POSTER_ORDER + [s for s in parts if s not in POSTER_ORDER]:
        p = parts.get(src)
        if p:
            out.posters += [u for u in p.posters if u not in out.posters]
    seen: set[str] = set()
    for src in order:
        p = parts.get(src)
        if p:
            for g in p.genres:
                if g.lower() not in seen:
                    seen.add(g.lower())
                    out.genres.append(g)
    wiki = parts.get("wikipedia")
    out.extract = wiki.extract if wiki else None
    out.warnings = [w for p in parts.values() for w in p.warnings]
    return out
