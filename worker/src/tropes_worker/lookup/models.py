"""Shapes shared by the resolver, the per-site fetchers and the merge step."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Site keys, as stored in media_link.site and shown in the links line (web/src/lib/media.ts names them).
SITES = (
    "wikipedia", "imdb", "tmdb", "tvdb", "letterboxd", "rt", "metacritic", "mal", "anidb", "ann",
    "steam", "goodreads", "openlibrary", "musicbrainz", "spotify", "bandcamp", "itunes", "official",
)


@dataclass
class Candidate:
    """One possible identity for a log entry."""

    qid: str | None
    label: str
    description: str = ""
    year: int | None = None
    creator: str | None = None
    # Wikidata P31 labels or qids, lowercased ("television series", "film"); empty for per-site hits.
    kinds: list[str] = field(default_factory=list)
    # External ids keyed as in media.external_ids: imdb, tmdb_tv, tmdb_movie, tvdb, mal, anidb, ann, rt, metacritic,
    # steam, goodreads, openlibrary, musicbrainz_rg, spotify, itunes, letterboxd, official (a URL).
    ids: dict[str, str] = field(default_factory=dict)
    wikipedia: str | None = None  # English article title
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    # Where it came from: "seed" (Notion Media Link), "wikidata", or a site key for a per-site search fallback.
    source: str = "wikidata"
    sitelinks: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Link:
    url: str
    score: str | None = None  # display text: "77", "100%", "6.21", "4.17"
    score_value: float | None = None


@dataclass
class Partial:
    """What one fetcher contributes. merge() combines partials with a fixed precedence."""

    details: dict[str, Any] = field(default_factory=dict)
    links: dict[str, Link] = field(default_factory=dict)
    # Poster URLs, best first. The merge keeps the list order per precedence.
    posters: list[str] = field(default_factory=list)
    # Genre strings as the source gives them ("Sci-Fi & Fantasy", "Action", "science fiction").
    genres: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    extract: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "details": self.details,
            "links": {k: asdict(v) for k, v in self.links.items()},
            "posters": self.posters,
            "genres": self.genres,
            "ids": self.ids,
            "extract": self.extract,
            "warnings": self.warnings,
        }


# Detail keys by type, so fetchers agree on names. Dates are ISO strings (YYYY, YYYY-MM or YYYY-MM-DD).
#   TV:      start, end, seasons, episodes, network, studio (anime), source_material (anime), status
#   Movie:   start (release), runtime_min, studio, director
#   Book:    start (first published), author, pages
#   Game:    start (release), developer, publisher, platforms
#   Album:   start (release), artist, tracks, label
#   Podcast: start (first episode), end, network, episodes
DETAIL_KEYS = ("start", "end", "seasons", "episodes", "network", "studio", "source_material", "status", "runtime_min",
               "director", "author", "pages", "developer", "publisher", "platforms", "artist", "tracks", "label")
