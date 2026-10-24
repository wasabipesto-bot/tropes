"""Open Library works API for fetch, search.json for search. No key needed."""

from __future__ import annotations

from .http import Fetcher
from .models import Candidate, Link, Partial


def fetch(f: Fetcher, ids: dict[str, str], *, type_: str, settings) -> Partial | None:
    oid = ids.get("openlibrary")
    if not oid:
        return None
    work_id = oid
    if oid.upper().endswith("M"):  # an edition id; follow it to its work
        edition = f.get_json(f"https://openlibrary.org/books/{oid}.json")
        if not edition:
            return None
        works = edition.get("works") or []
        key = works[0].get("key") if works else None
        if not key:
            return None
        work_id = key.rsplit("/", 1)[-1]

    work = f.get_json(f"https://openlibrary.org/works/{work_id}.json")
    if not work:
        return None

    details: dict[str, object] = {}
    start = work.get("first_publish_date")
    if start:
        details["start"] = start

    author_key = (((work.get("authors") or [{}])[0]).get("author") or {}).get("key")
    if author_key:
        author = f.get_json(f"https://openlibrary.org{author_key}.json")
        if author and author.get("name"):
            details["author"] = author["name"]

    genres = list((work.get("subjects") or [])[:15])

    posters = []
    covers = work.get("covers") or []
    if covers and isinstance(covers[0], int) and covers[0] > 0:
        posters.append(f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg")

    links = {"openlibrary": Link(url=f"https://openlibrary.org/works/{work_id}")}

    return Partial(details=details, links=links, posters=posters, genres=genres, ids={"openlibrary": work_id})


def search(f: Fetcher, title: str, creator: str | None, year: int | None, *, type_: str, settings) -> list[Candidate]:
    params = {"title": title, "limit": 10, "fields": "key,title,author_name,first_publish_year,cover_i"}
    if creator:
        params["author"] = creator
    data = f.get_json("https://openlibrary.org/search.json", params=params)
    if not data:
        return []
    out = []
    for doc in (data.get("docs") or [])[:10]:
        key = doc.get("key")
        if not key or not doc.get("title"):
            continue
        authors = doc.get("author_name") or []
        out.append(
            Candidate(
                qid=None,
                label=doc["title"],
                ids={"openlibrary": key.rsplit("/", 1)[-1]},
                creator=authors[0] if authors else None,
                year=doc.get("first_publish_year"),
                kinds=["literary work"],
                source="openlibrary",
            )
        )
    return out
