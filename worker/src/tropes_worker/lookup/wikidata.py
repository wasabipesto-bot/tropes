"""Wikidata as the identity hub: search, entities, claims, and what one item tells us."""

from __future__ import annotations

import re
from typing import Any

from .http import Fetcher
from .models import Candidate, Link, Partial

API = "https://www.wikidata.org/w/api.php"

# Accepted instance-of (P31) classes per log type. Unknown classes are neither accepted nor rejected.
CLASSES: dict[str, set[str]] = {
    "TV Series": {"Q5398426", "Q117467246", "Q63952888", "Q581714", "Q1259759", "Q526877", "Q15416", "Q21188110", "Q7724161"},
    "Movie": {"Q11424", "Q202866", "Q20650540", "Q24869", "Q506240", "Q29168811", "Q93204", "Q24862", "Q17517379"},
    "Book": {
        "Q7725634",
        "Q8261",
        "Q571",
        "Q47461344",
        "Q3331189",
        "Q149537",
        "Q49084",
        "Q1004",
        "Q8274",
        "Q725377",
        "Q213369",
        "Q747381",
        "Q21198342",
        "Q1760610",
        "Q17537576",
        "Q277759",
        "Q1667921",
    },
    "Game": {"Q7889", "Q209163", "Q1066707", "Q865493"},
    "Album": {"Q482994", "Q208569", "Q169930", "Q222910", "Q209939", "Q4164344", "Q217199"},
    "Podcast": {"Q24634210"},
}
CLASSES["Other"] = set().union(*CLASSES.values())
# Classes that are never a log entry: seasons, episodes, people, characters, bands, songs, places, articles, series containers.
REJECTED: set[str] = {
    "Q3464665",
    "Q21191270",
    "Q61855877",
    "Q5",
    "Q15632617",
    "Q102408544",
    "Q80447738",
    "Q95074",
    "Q215380",
    "Q5741069",
    "Q105543609",
    "Q55850593",
    "Q55850643",
    "Q7366",
    "Q134556",
    "Q101352",
    "Q515",
    "Q1549591",
    "Q13442814",
    "Q13406463",
    "Q7058673",
    "Q838795",
    "Q1886349",
    "Q14660",
    "Q4167410",
    "Q2085381",
    "Q6881511",
    "Q4830453",
    "Q7397",
    "Q341",
    "Q205020",
    "Q783866",
    "Q1639024",
    "Q24529780",
}
# Series containers are rejected for the types where the log entry is a single work.
SERIES_FOR = {"Book": {"Q277759", "Q1667921"}}
EDITIONS = {"Q3331189", "Q57933693", "Q47461344"} - {"Q47461344"}  # version/edition/translation, book edition

# External id properties → keys in media.external_ids.
ID_PROPS = {
    "P345": "imdb",
    "P4983": "tmdb_tv",
    "P4947": "tmdb_movie",
    "P4835": "tvdb",
    "P4086": "mal",
    "P5646": "anidb",
    "P1985": "ann",
    "P1258": "rt",
    "P1712": "metacritic",
    "P1733": "steam",
    "P2969": "goodreads",
    "P8383": "goodreads_work",
    "P648": "openlibrary",
    "P436": "musicbrainz_rg",
    "P2205": "spotify",
    "P5842": "itunes",
    "P2281": "itunes_album",
    "P6127": "letterboxd",
}
# Seeds from the Notion Media Link: id key → property.
SEED_PROPS = {
    "imdb": "P345",
    "steam": "P1733",
    "goodreads": "P2969",
    "spotify": "P2205",
    "tmdb_tv": "P4983",
    "tmdb_movie": "P4947",
    "mal": "P4086",
    "openlibrary": "P648",
    "musicbrainz_rg": "P436",
    "itunes": "P5842",
}
CREATOR_PROPS = ("P57", "P50", "P178", "P175", "P449", "P272", "P170", "P1040", "P2515", "P86")
# Review scores with the reviewer as a qualifier; the ones we show for albums (D8).
REVIEWERS = {"Q31181": "AllMusic", "Q19828811": "Album of the Year", "Q150248": "Metacritic", "Q1150452": "Pitchfork"}


def _vals(entity: dict[str, Any], prop: str) -> list[Any]:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if v is not None:
            out.append(v)
    return out


def _qids(entity: dict[str, Any], prop: str) -> list[str]:
    return [v["id"] for v in _vals(entity, prop) if isinstance(v, dict) and "id" in v]


def _strings(entity: dict[str, Any], prop: str) -> list[str]:
    return [v for v in _vals(entity, prop) if isinstance(v, str)]


def _time(v: dict[str, Any]) -> str | None:
    """A Wikidata time value as an ISO date trimmed to its precision (9 year, 10 month, 11 day)."""
    t = v.get("time", "")
    m = re.match(r"\+(\d{4})-(\d{2})-(\d{2})", t)
    if not m:
        return None
    p = v.get("precision", 11)
    if p <= 9:
        return m.group(1)
    if p == 10:
        return f"{m.group(1)}-{m.group(2)}"
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _dates(entity: dict[str, Any], prop: str) -> list[str]:
    out = [d for d in (_time(v) for v in _vals(entity, prop) if isinstance(v, dict)) if d]
    return sorted(out)


def _quantity(entity: dict[str, Any], prop: str) -> int | None:
    for v in _vals(entity, prop):
        if isinstance(v, dict) and "amount" in v:
            try:
                return int(float(v["amount"]))
            except ValueError:
                continue
    return None


# Wikidata keeps labels that are the same in every language under "mul"; English falls back to it.
LANGS = "en|mul"


def _label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels", {})
    return labels.get("en", labels.get("mul", {})).get("value", "")


def _aliases(entity: dict[str, Any]) -> list[str]:
    aliases = entity.get("aliases", {})
    return [a["value"] for lang in ("en", "mul") for a in aliases.get(lang, [])]


# Requests ----------------------------------------------------------------------------------------


def _query_text(title: str) -> str:
    # Colons and quotes have meaning to CirrusSearch; a title is plain words to it.
    return re.sub(r"[:\"'`()\[\]{}!?~*]", " ", title).strip()


def search(f: Fetcher, title: str, type_: str, limit: int = 10) -> list[str]:
    """Candidate qids: label search, then full-text search restricted to the type's classes, then a fuzzy retry."""
    seen: list[str] = []

    def add(ids: list[str]) -> None:
        for q in ids:
            if q not in seen:
                seen.append(q)

    d = f.get_json(
        API, {"action": "wbsearchentities", "search": title, "language": "en", "type": "item", "limit": limit, "format": "json"}
    )
    add([r["id"] for r in (d or {}).get("search", [])])
    classes = "|".join(f"P31={q}" for q in sorted(CLASSES.get(type_, CLASSES["Other"])))
    text = _query_text(title)
    for q in (text, " ".join(w + "~" for w in text.split() if len(w) > 3)):
        if not q:
            continue
        d = f.get_json(
            API,
            {
                "action": "query",
                "list": "search",
                "srsearch": f"{q} haswbstatement:{classes}",
                "srlimit": limit,
                "format": "json",
            },
        )
        hits = [r["title"] for r in (d or {}).get("query", {}).get("search", [])]
        add(hits)
        if hits:
            break
    return seen[: limit + 5]


def by_seed(f: Fetcher, key: str, value: str) -> list[str]:
    """Items carrying an external id (exact)."""
    prop = SEED_PROPS.get(key)
    if not prop:
        return []
    d = f.get_json(
        API, {"action": "query", "list": "search", "srsearch": f"haswbstatement:{prop}={value}", "srlimit": 5, "format": "json"}
    )
    return [r["title"] for r in (d or {}).get("query", {}).get("search", [])]


def entities(f: Fetcher, qids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(qids), 50):
        d = f.get_json(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(qids[i : i + 50]),
                "props": "labels|descriptions|aliases|claims|sitelinks",
                "languages": LANGS,
                "sitefilter": "enwiki",
                "format": "json",
            },
        )
        out.update({q: e for q, e in (d or {}).get("entities", {}).items() if "missing" not in e})
    return out


def labels(f: Fetcher, qids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    qids = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(qids), 50):
        d = f.get_json(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(qids[i : i + 50]),
                "props": "labels",
                "languages": LANGS,
                "format": "json",
            },
        )
        for q, e in (d or {}).get("entities", {}).items():
            out[q] = _label(e) or q
    return out


# Reading an item -----------------------------------------------------------------------------------


def linked_qids(entity: dict[str, Any]) -> list[str]:
    """Every qid a candidate needs labels for: classes, creators, genres, reviewers."""
    ids = _qids(entity, "P31") + _qids(entity, "P136")
    for p in CREATOR_PROPS:
        ids += _qids(entity, p)
    return ids


def year_of(entity: dict[str, Any]) -> int | None:
    dates = _dates(entity, "P577") + _dates(entity, "P580") + _dates(entity, "P571")
    return int(min(dates)[:4]) if dates else None


def ids_of(entity: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for prop, key in ID_PROPS.items():
        vals = _strings(entity, prop)
        if vals:
            ids[key] = vals[0]
    sites = _strings(entity, "P856")
    if sites:
        ids["official"] = sites[0]
    return ids


def candidate(entity: dict[str, Any], names: dict[str, str]) -> Candidate:
    creators = [names.get(q, q) for p in CREATOR_PROPS for q in _qids(entity, p)]
    sitelinks = entity.get("sitelinks", {})
    return Candidate(
        qid=entity["id"],
        label=_label(entity),
        description=entity.get("descriptions", {}).get("en", {}).get("value", ""),
        year=year_of(entity),
        creator=", ".join(dict.fromkeys(creators)) or None,
        kinds=[names.get(q, q).lower() for q in _qids(entity, "P31")],
        ids=ids_of(entity),
        wikipedia=sitelinks.get("enwiki", {}).get("title") if isinstance(sitelinks, dict) else None,
        source="wikidata",
        sitelinks=len(sitelinks) if isinstance(sitelinks, dict) else 0,
    )


def class_qids(entity: dict[str, Any]) -> list[str]:
    return _qids(entity, "P31")


def work_of(entity: dict[str, Any]) -> str | None:
    """For an edition item, the work it is an edition of (P629)."""
    w = _qids(entity, "P629")
    return w[0] if w else None


def is_edition(entity: dict[str, Any]) -> bool:
    return any(q in EDITIONS for q in class_qids(entity))


def editions_of(entity: dict[str, Any]) -> list[str]:
    return _qids(entity, "P747")[:6]


def partial(entity: dict[str, Any], names: dict[str, str], type_: str) -> Partial:
    """What Wikidata itself can fill in: a fallback behind the per-site fetchers."""
    p = Partial(ids=ids_of(entity))
    d = p.details
    start = _dates(entity, "P580") or _dates(entity, "P577")
    end = _dates(entity, "P582")
    if start:
        d["start"] = start[0]
    if end:
        d["end"] = end[-1]
    if type_ == "TV Series":
        if (n := _quantity(entity, "P2437")) is not None:
            d["seasons"] = n
        if (n := _quantity(entity, "P1113")) is not None:
            d["episodes"] = n
        nets = [names.get(q, q) for q in _qids(entity, "P449")]
        if nets:
            d["network"] = nets[0]
    if type_ == "Movie":
        if (n := _quantity(entity, "P2047")) is not None:
            d["runtime_min"] = n
        directors = [names.get(q, q) for q in _qids(entity, "P57")]
        if directors:
            d["director"] = ", ".join(directors)
    if type_ == "Book":
        authors = [names.get(q, q) for q in _qids(entity, "P50")]
        if authors:
            d["author"] = ", ".join(authors)
        if (n := _quantity(entity, "P1104")) is not None:
            d["pages"] = n
    if type_ == "Game":
        devs = [names.get(q, q) for q in _qids(entity, "P178")]
        pubs = [names.get(q, q) for q in _qids(entity, "P123")]
        if devs:
            d["developer"] = ", ".join(devs)
        if pubs:
            d["publisher"] = ", ".join(pubs)
    if type_ == "Album":
        artists = [names.get(q, q) for q in _qids(entity, "P175")]
        if artists:
            d["artist"] = ", ".join(artists)
        if (n := _quantity(entity, "P2635")) is not None:
            d["tracks"] = n
    p.genres = [names.get(q, q) for q in _qids(entity, "P136")]
    sitelinks = entity.get("sitelinks", {})
    if isinstance(sitelinks, dict) and "enwiki" in sitelinks:
        p.links["wikipedia"] = Link(url=f"https://en.wikipedia.org/wiki/{sitelinks['enwiki']['title'].replace(' ', '_')}")
    for key, value in p.ids.items():
        url = link_url(key, value)
        if url and _site_of(key) not in p.links:
            p.links[_site_of(key)] = Link(url=url)
    # Album review scores (P444, qualified by reviewer P447), shown as "AllMusic 4.5" style links.
    for c in entity.get("claims", {}).get("P444", []):
        score = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        who = [q.get("datavalue", {}).get("value", {}).get("id") for q in c.get("qualifiers", {}).get("P447", [])]
        name = next((REVIEWERS[q] for q in who if q in REVIEWERS), None)
        if isinstance(score, str) and name:
            d.setdefault("reviews", []).append({"by": name, "score": score})
    return p


def _site_of(key: str) -> str:
    return {
        "tmdb_tv": "tmdb",
        "tmdb_movie": "tmdb",
        "goodreads_work": "goodreads",
        "musicbrainz_rg": "musicbrainz",
        "itunes_album": "itunes",
    }.get(key, key)


def link_url(key: str, value: str) -> str | None:
    return {
        "imdb": f"https://www.imdb.com/title/{value}/",
        "tmdb_tv": f"https://www.themoviedb.org/tv/{value}",
        "tmdb_movie": f"https://www.themoviedb.org/movie/{value}",
        "tvdb": f"https://thetvdb.com/dereferrer/series/{value}",
        "mal": f"https://myanimelist.net/anime/{value}",
        "anidb": f"https://anidb.net/anime/{value}",
        "ann": f"https://www.animenewsnetwork.com/encyclopedia/anime.php?id={value}",
        "rt": f"https://www.rottentomatoes.com/{value}",
        "metacritic": f"https://www.metacritic.com/{value}",
        "steam": f"https://store.steampowered.com/app/{value}/",
        "goodreads": f"https://www.goodreads.com/book/show/{value}",
        "goodreads_work": f"https://www.goodreads.com/work/editions/{value}",
        "openlibrary": f"https://openlibrary.org/works/{value}"
        if value.endswith("W")
        else f"https://openlibrary.org/books/{value}",
        "musicbrainz_rg": f"https://musicbrainz.org/release-group/{value}",
        "spotify": f"https://open.spotify.com/album/{value}",
        "itunes": f"https://podcasts.apple.com/podcast/id{value}",
        "itunes_album": f"https://music.apple.com/album/{value}",
        "letterboxd": f"https://letterboxd.com/film/{value}/",
        "official": value,
    }.get(key)
