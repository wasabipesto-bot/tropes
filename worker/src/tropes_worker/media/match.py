"""Match log entries to folders on the media disk (plan T2), and books to Calibre's library."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from ..lookup.resolve import creator_match, norm
from .listing import Folder, Listing, episode_of, sidecar_subs

FOLDER_RX = re.compile(r"^(.*?)\s*[\[(](\d{4})[\])]")
TITLE_YEAR_RX = re.compile(r"^(.*\S)\s*\((\d{4})\)\s*$")
# Titles the log writes one way and folders another.
ALIASES = {
    "star wars a new hope": ["star wars episode iv a new hope", "star wars"],
    "star wars the empire strikes back": ["star wars episode v the empire strikes back"],
    "star wars return of the jedi": ["star wars episode vi return of the jedi"],
    "star wars the phantom menace": ["star wars episode i the phantom menace"],
    "star wars attack of the clones": ["star wars episode ii attack of the clones"],
    "star wars revenge of the sith": ["star wars episode iii revenge of the sith"],
    "star wars the force awakens": ["star wars episode vii the force awakens"],
    "star wars the last jedi": ["star wars episode viii the last jedi"],
    "star wars the rise of skywalker": ["star wars episode ix the rise of skywalker"],
    "harry potter and the philosopher s stone": ["harry potter and the sorcerer's stone"],
    "the final empire": ["mistborn the final empire", "mistborn"],
}


def parse_folder(name: str) -> tuple[str, int | None]:
    """ "Children of Men (2006)" → ("Children of Men", 2006); "Food Wars [Shokugeki no Souma] [2015] [1080p]" →
    ("Food Wars", 2015); "Sandman, The" → ("The Sandman", None); "The Avengers 4 - Endgame (2019)" keeps its
    number for title_keys to drop."""
    m = FOLDER_RX.match(name)
    title, year = (m.group(1), int(m.group(2))) if m else (name, None)
    title = re.sub(r"\s*\[.*?\]\s*", " ", title).strip()
    sm = re.match(r"^(.*),\s*(The|A|An)$", title, re.I)
    if sm:
        title = f"{sm.group(2)} {sm.group(1)}"
    return title, year


def parse_title(title: str) -> tuple[str, int | None]:
    """A log title that carries its year, "Dune (1984)", gives the year up."""
    m = TITLE_YEAR_RX.match(title)
    return (m.group(1), int(m.group(2))) if m else (title, None)


_SIMPLIFY = (
    lambda k: re.sub(r"^(the|a|an) ", "", k),  # leading article
    lambda k: re.sub(r"\b(the|a|an|and|of)\b", " ", k),  # small words
    lambda k: re.sub(r"\b\d{1,2}\b", " ", k),  # a franchise number: "Harry Potter 4 - The Goblet of Fire"
    lambda k: re.sub(r"\bpart (\d)\b", r"part\1", k),
)


def title_keys(title: str) -> list[str]:
    """Normalised forms of a title that two naming habits might share, built by applying every simplification
    in every combination (article, small words, franchise number) and finally dropping spaces ("Mushishi")."""
    n = norm(parse_title(title)[0])
    keys = [n] + [norm(a) for a in ALIASES.get(n, [])]
    frontier = list(keys)
    while frontier:
        nxt = []
        for k in frontier:
            for f in _SIMPLIFY:
                v = re.sub(r"\s+", " ", f(k)).strip()
                if v and v not in keys:
                    keys.append(v)
                    nxt.append(v)
        frontier = nxt
    keys += [k.replace(" ", "") for k in keys]
    return [k for k in dict.fromkeys(keys) if k]


@dataclass
class VideoMatch:
    folder: Folder
    year_ok: bool  # the folder's year agrees with the entry's (within one), or neither is known
    exact_year: bool = False
    episodes: list[tuple[int, int, Any]] = field(default_factory=list)  # (season, episode, Entry)
    films: list[Any] = field(default_factory=list)  # Entries for a film (main file first)

    @property
    def confident(self) -> bool:
        return self.year_ok


def _year_agrees(folder_year: int | None, entry_year: int | None) -> bool | None:
    """Release years differ by one between sources (festival against wide release), so one year off still agrees."""
    if folder_year is None or entry_year is None:
        return None
    return abs(folder_year - entry_year) <= 1


def match_video(entry: dict[str, Any], folders: list[Folder], index: dict[str, list[Folder]] | None = None) -> list[VideoMatch]:
    """Folders whose name is the entry's title; confident when the year agrees (films exactly, series within a year)."""
    if index is None:
        index = folder_index(folders)
    want_series = entry["type"] == "TV Series"
    title, title_year = parse_title(entry["title"])
    year = entry.get("year") or title_year
    out: list[VideoMatch] = []
    seen: set[str] = set()
    keys = title_keys(title)
    candidates: list[tuple[Folder, bool | None]] = [(f, True) for key in keys for f in index.get(key, [])]
    # A folder whose name is a prefix or suffix of the title (or the reverse) still counts when the year agrees
    # ("Scott Pilgrim (2023)"), and is offered as a check when the folder has no year and differs by one word
    # ("Penny Dreadful X", "Marvel's What If.!").
    for f in folders:
        if f.is_series != want_series:
            continue
        ftitle, fyear = parse_folder(f.name)
        fk = norm(ftitle)
        if not fk:
            continue
        near = any(
            (k.startswith(fk + " ") or k.endswith(" " + fk) or fk.startswith(k + " ") or fk.endswith(" " + k)) for k in keys[:2]
        )
        if not near:
            continue
        if year and fyear == year:
            candidates.append((f, False))
        elif fyear is None and abs(len(fk.split()) - len(keys[0].split())) <= 1:
            candidates.append((f, None))
    for f, exact in candidates:
        if f.path in seen:
            continue
        seen.add(f.path)
        if f.is_series != want_series:
            continue
        if True:
            _, fyear = parse_folder(f.name)
            agree = _year_agrees(fyear, year)
            # exact: the title matched outright; False: a near name with the year agreeing; None: a near name, no year, a check.
            ok = agree is not False and (exact is True or (exact is False and agree is True))
            m = VideoMatch(folder=f, year_ok=ok, exact_year=(fyear == year and fyear is not None))
            if want_series:
                for v in sorted(f.videos, key=lambda e: e.path):
                    ep = episode_of(v.path)
                    if ep:
                        m.episodes.append((ep[0], ep[1], v))
                m.episodes.sort(key=lambda t: (t[0], t[1]))
            else:
                m.films = sorted(f.videos, key=lambda e: -e.size)
            out.append(m)
    out.sort(key=lambda m: (not m.year_ok, not m.exact_year, -len(m.episodes) - len(m.films)))
    return out


def best_video(matches: list[VideoMatch]) -> tuple[VideoMatch | None, str]:
    """One folder, or why not: 'none', 'ambiguous' (two confident folders of different years), 'year' (only mismatches)."""
    conf = [m for m in matches if m.year_ok]
    if not matches:
        return None, "none"
    if not conf:
        return None, "year"
    years = {parse_folder(m.folder.name)[1] for m in conf}
    if len(conf) > 1 and len(years) > 1 and not any(m.exact_year for m in conf):
        return None, "ambiguous"
    return conf[0], "ok"


def folder_index(folders: list[Folder]) -> dict[str, list[Folder]]:
    index: dict[str, list[Folder]] = {}
    for f in folders:
        title, _ = parse_folder(f.name)
        for key in title_keys(title):
            index.setdefault(key, []).append(f)
    return index


# Books -----------------------------------------------------------------------------------


@dataclass
class BookMatch:
    book_id: int
    title: str
    author: str
    path: str  # the book's folder, relative to the Calibre root
    files: dict[str, str]  # format → file name without extension (Calibre's data table)
    by: str  # isbn | goodreads | title+author | title

    @property
    def formats(self) -> list[str]:
        return list(self.files)

    def file(self, root: str = "Books") -> str | None:
        """The file to read: EPUB first, then MOBI or AZW3 (unpacked on the worker)."""
        for fmt in ("EPUB", "MOBI", "AZW3"):
            if fmt in self.files:
                return f"{root}/{self.path}/{self.files[fmt]}.{fmt.lower()}"
        return None


def _calibre_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        "select b.id, b.title, b.path, (select group_concat(a.name, ' & ') from books_authors_link l "
        "join authors a on a.id=l.author where l.book=b.id) as author from books b"
    ).fetchall()
    ids = db.execute("select book, type, val from identifiers").fetchall()
    by_book: dict[int, dict[str, str]] = {}
    for book, typ, val in ids:
        by_book.setdefault(book, {})[typ] = val
    files: dict[int, dict[str, str]] = {}
    for book, fmt, name in db.execute("select book, format, name from data").fetchall():
        files.setdefault(book, {})[fmt] = name
    return [
        {
            "id": r[0],
            "title": r[1],
            "path": r[2],
            "author": r[3] or "",
            "files": files.get(r[0], {}),
            "ids": by_book.get(r[0], {}),
        }
        for r in rows
    ]


def match_book(entry: dict[str, Any], calibre: sqlite3.Connection, rows: list[dict[str, Any]] | None = None) -> BookMatch | None:
    """A Calibre book for a log entry: by ISBN or Goodreads id from the pinned identity, else title and author,
    else title alone."""
    rows = rows if rows is not None else _calibre_rows(calibre)
    ext = entry.get("externalIds") or {}
    want_isbn = {str(v).replace("-", "") for k, v in ext.items() if k == "isbn"}
    want_gr = {str(ext[k]) for k in ("goodreads", "goodreads_work") if k in ext}
    for r in rows:
        ids = r["ids"]
        if want_isbn and ids.get("isbn", "").replace("-", "") in want_isbn:
            return _book(r, "isbn")
        if want_gr and ids.get("goodreads") in want_gr:
            return _book(r, "goodreads")
    keys = set(title_keys(entry["title"]))
    creator = entry.get("creator") or ""
    same_author = lambda r: creator_match(creator, r["author"])  # noqa: E731
    titled = [r for r in rows if keys & set(r.setdefault("_keys", title_keys(r["title"])))]
    if not titled and creator:
        main = norm(entry["title"])
        # "Good Omens: The Nice and Accurate Prophecies…" for "Good Omens";
        # "The Time Paradox" for "Artemis Fowl and the Time Paradox".
        sub = re.sub(r"^.*?(?:: | and the | and )", "", entry["title"]) if re.search(r": | and the ", entry["title"]) else None
        subkeys = set(title_keys(sub)) if sub else set()
        titled = [
            r
            for r in rows
            if same_author(r) and (norm(r["title"]).startswith(main + " ") or (subkeys and subkeys & set(r["_keys"])))
        ]
    if not titled:
        return None
    if creator:
        for r in titled:
            if same_author(r):
                return _book(r, "title+author")
    if len(titled) == 1:
        return _book(titled[0], "title")
    with_epub = [r for r in titled if "EPUB" in r["files"]]
    return _book((with_epub or titled)[0], "title")


def _book(r: dict[str, Any], by: str) -> BookMatch:
    return BookMatch(book_id=r["id"], title=r["title"], author=r["author"], path=r["path"], files=dict(r["files"]), by=by)


def calibre_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return _calibre_rows(db)


__all__ = [
    "match_video",
    "match_book",
    "calibre_rows",
    "folder_index",
    "parse_folder",
    "title_keys",
    "VideoMatch",
    "BookMatch",
    "sidecar_subs",
    "Listing",
]
