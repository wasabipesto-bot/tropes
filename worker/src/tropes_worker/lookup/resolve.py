"""Identity resolution (plan T2): one log entry → the Wikidata item it refers to, or none.

Deterministic. Exact seeds from the Notion Media Link win outright; otherwise
candidates from a Wikidata search are scored on title, class, creator and year,
and the margin between the top two decides whether the result is confident,
needs a check (the model breaks the tie, in the job), or was not found.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from . import wikidata
from .http import Fetcher
from .models import Candidate

CONFIDENT_SCORE = 0.75
CONFIDENT_MARGIN = 0.2
CHECK_SCORE = 0.45
STOPWORDS = {
    "the",
    "and",
    "of",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "studio",
    "studios",
    "entertainment",
    "games",
    "game",
    "inc",
    "ltd",
    "llc",
    "co",
    "company",
    "productions",
    "pictures",
    "films",
    "records",
    "music",
    "team",
}


@dataclass
class Entry:
    id: int
    title: str
    type: str
    creator: str | None = None
    logged_year: int | None = None
    media_url: str | None = None


@dataclass
class Resolution:
    status: str  # confident | check | not_found
    chosen: Candidate | None
    candidates: list[Candidate] = field(default_factory=list)
    seed: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "chosen": self.chosen.as_dict() if self.chosen else None,
            "candidates": [c.as_dict() for c in self.candidates],
            "seed": self.seed,
            "notes": self.notes,
        }


# Seeds -------------------------------------------------------------------------------------------

SEED_PATTERNS = [
    ("imdb", re.compile(r"imdb\.com/title/(tt\d+)")),
    ("steam", re.compile(r"store\.steampowered\.com/app/(\d+)")),
    ("goodreads", re.compile(r"goodreads\.com/book/show/(\d+)")),
    ("spotify", re.compile(r"open\.spotify\.com/album/([A-Za-z0-9]+)")),
]


def seed_from_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    for key, rx in SEED_PATTERNS:
        m = rx.search(url)
        if m:
            return key, m.group(1)
    return None


# Scoring -----------------------------------------------------------------------------------------


def norm(s: str) -> str:
    s = (
        s.replace("Æ", "Ae")
        .replace("æ", "ae")
        .replace("Ø", "O")
        .replace("ø", "o")
        .replace("ß", "ss")
        .replace("Œ", "Oe")
        .replace("œ", "oe")
    )
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\s*\((?:tv series|television series|film|novel|video game|album|series|book|miniseries|anime)\)\s*$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _no_article(s: str) -> str:
    return re.sub(r"^(the|a|an) ", "", s)


def title_match(title: str, label: str, aliases: list[str]) -> tuple[float, str]:
    t = norm(title)
    names = [norm(label)] + [norm(a) for a in aliases]
    names = [n for n in names if n]
    if t in names or _no_article(t) in [_no_article(n) for n in names]:
        return 0.5, "title matches"
    for n in names:
        if len(t) >= 4 and len(n) >= 4 and (n.startswith(t) or t.startswith(n) or f" {t} " in f" {n} " or f" {n} " in f" {t} "):
            return 0.2, "title partly matches"
    return 0.0, "title differs"


def creator_match(creator: str | None, candidate_creator: str | None) -> bool:
    if not creator or not candidate_creator:
        return False
    a = {w for w in norm(creator).split() if len(w) >= 3 and w not in STOPWORDS}
    b = {w for w in norm(candidate_creator).split() if len(w) >= 3 and w not in STOPWORDS}
    return bool(a & b)


def score(entry: Entry, cand: Candidate, classes: list[str], aliases: list[str]) -> tuple[float, list[str]]:
    s, why = title_match(entry.title, cand.label, aliases)
    reasons = [why]
    accepted = wikidata.CLASSES.get(entry.type, wikidata.CLASSES["Other"])
    rejected = wikidata.REJECTED | wikidata.SERIES_FOR.get(entry.type, set())
    if any(q in rejected for q in classes):
        s -= 0.6
        reasons.append("wrong kind of thing")
    elif any(q in accepted for q in classes):
        s += 0.3
        reasons.append("right kind")
    elif classes:
        s -= 0.1
        reasons.append("unknown kind")
    if creator_match(entry.creator, cand.creator):
        s += 0.25
        reasons.append("creator matches")
    if entry.logged_year and cand.year and cand.year > entry.logged_year:
        s -= 0.5
        reasons.append(f"released {cand.year}, after it was logged")
    s += min(cand.sitelinks, 20) * 0.005
    return round(s, 3), reasons


# Resolution --------------------------------------------------------------------------------------


def resolve(f: Fetcher, entry: Entry, *, shared_links: set[str] = frozenset()) -> Resolution:
    seed = seed_from_url(entry.media_url)
    seed_qids: list[str] = []
    seed_note = None
    if seed and entry.media_url not in shared_links:
        seed_qids = wikidata.by_seed(f, *seed)
        seed_note = f"{seed[0]} {seed[1]}"
    qids = seed_qids or wikidata.search(f, entry.title, entry.type)
    if not qids:
        return _parent_show(f, entry, shared_links) or Resolution("not_found", None, notes=["no Wikidata results"])
    ents = wikidata.entities(f, qids)
    # Editions stand in for their work: fetch the works too, so the edition can fold into it below.
    works = [w for e in ents.values() if wikidata.is_edition(e) and (w := wikidata.work_of(e)) and w not in ents]
    if works:
        ents.update(wikidata.entities(f, works))
        qids = qids + works
    names = wikidata.labels(f, [q for e in ents.values() for q in wikidata.linked_qids(e)])
    cands: list[Candidate] = []
    for q in qids:
        e = ents.get(q)
        if not e:
            continue
        c = wikidata.candidate(e, names)
        c.score, c.reasons = score(entry, c, wikidata.class_qids(e), wikidata._aliases(e))
        if q in seed_qids:
            c.score, c.reasons, c.source = 1.0, [f"Notion link: {seed_note}"], "seed"
        cands.append(c)
    cands = _fold_editions(cands, ents)
    cands.sort(key=lambda c: -c.score)
    cands = cands[:6]
    if not cands:
        return Resolution("not_found", None, notes=["no readable Wikidata items"])
    top = cands[0]
    second = cands[1].score if len(cands) > 1 else -1.0
    if top.source == "seed":
        status = "confident"
    elif top.score >= CONFIDENT_SCORE and top.score - second >= CONFIDENT_MARGIN:
        status = "confident"
    elif top.score >= CHECK_SCORE:
        status = "check"
    else:
        return _parent_show(f, entry, shared_links) or Resolution(
            "not_found", None, cands, seed_note, ["nothing scored well enough"]
        )
    return Resolution(status, top, cands, seed_note)


def _fold_editions(cands: list[Candidate], ents: dict[str, Any]) -> list[Candidate]:
    """Merge each edition into its work: the work keeps the best score and gains the edition's Goodreads id."""
    by_qid = {c.qid: c for c in cands}
    out: list[Candidate] = []
    for c in cands:
        e = ents.get(c.qid or "")
        work = wikidata.work_of(e) if e and wikidata.is_edition(e) else None
        if work and work in by_qid:
            w = by_qid[work]
            if c.score > w.score or c.source == "seed":
                w.score, w.source = c.score, c.source
                w.reasons = c.reasons + ["via an edition"]
            if "goodreads" in c.ids and "goodreads" not in w.ids:
                w.ids["goodreads"] = c.ids["goodreads"]
            continue
        out.append(c)
    return out


def _parent_show(f: Fetcher, entry: Entry, shared_links: set[str]) -> Resolution | None:
    """ "Friends at the Table: Marielda" is a season of a podcast Wikidata knows only as a whole: offer the parent as a check."""
    if ":" not in entry.title:
        return None
    parent = entry.title.split(":", 1)[0].strip()
    if len(parent) < 4:
        return None
    r = resolve(f, Entry(entry.id, parent, entry.type, entry.creator, entry.logged_year, None), shared_links=shared_links)
    if r.status == "not_found" or not r.chosen:
        return None
    r.status = "check"
    r.chosen.reasons = r.chosen.reasons + [f"matched the parent title “{parent}”"]
    return r


def from_site_hit(f: Fetcher, entry: Entry, hit: Candidate) -> Candidate:
    """A per-site hit whose id Wikidata also carries becomes the Wikidata item, with the site id kept."""
    for key, value in hit.ids.items():
        qids = wikidata.by_seed(f, key, value)
        if not qids:
            continue
        ents = wikidata.entities(f, qids[:1])
        e = ents.get(qids[0])
        if not e:
            continue
        c = wikidata.candidate(e, wikidata.labels(f, wikidata.linked_qids(e)))
        c.ids = {**c.ids, **hit.ids}
        c.score, c.reasons, c.source = 0.9, hit.reasons + [f"Wikidata item carrying the same {key} id"], hit.source
        return c
    return hit
