"""IMDb ratings from the public title.ratings.tsv.gz dataset (personal, non-commercial use), refreshed every
30 days. No page fetches: one gzip download, then a streamed scan for the ids we want."""

from __future__ import annotations

import gzip
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from .http import Fetcher
from .models import Link, Partial

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
MAX_AGE_DAYS = 30
TCONST = re.compile(r"tt\d+")

# One download at a time, even when a thread pool calls fetch() without a ratings dict.
_download = threading.Lock()


def dataset_path(settings) -> Path:
    return settings.lookup_cache_dir / "imdb" / "title.ratings.tsv.gz"


def ratings_for(f: Fetcher, settings, tconsts: set[str]) -> dict[str, tuple[float, int]]:
    """tconst -> (averageRating, numVotes) for the requested ids only. Titles under IMDb's vote floor are absent."""
    if not tconsts:
        return {}
    path = _ensure(f, dataset_path(settings))
    if path is None:
        return {}
    wanted, found = set(tconsts), {}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            next(fh, None)  # header: tconst, averageRating, numVotes
            for line in fh:
                tconst, _, rest = line.partition("\t")
                if tconst not in wanted:
                    continue
                rating, _, votes = rest.rstrip("\n").partition("\t")
                try:
                    found[tconst] = (float(rating), int(votes))
                except ValueError:
                    continue
                if len(found) == len(wanted):
                    break
    except (OSError, EOFError) as e:
        f.warn(f"imdb: ratings dataset unreadable ({type(e).__name__}), removed")
        path.unlink(missing_ok=True)
        return {}
    return found


def fetch(
    f: Fetcher, ids: dict[str, str], *, type_: str, settings, ratings: dict[str, tuple[float, int]] | None = None
) -> Partial | None:
    """The IMDb link, with the rating when the dataset has one. Pass `ratings` from one ratings_for() call when
    fetching many titles; without it each call rescans the dataset."""
    tconst = (ids.get("imdb") or "").strip()
    if not TCONST.fullmatch(tconst):
        return None
    if ratings is None:
        ratings = ratings_for(f, settings, {tconst})
    url = f"https://www.imdb.com/title/{tconst}/"
    hit = ratings.get(tconst)
    if hit is None:
        return Partial(links={"imdb": Link(url=url)})
    rating, _ = hit
    return Partial(links={"imdb": Link(url=url, score=f"{rating:.1f}", score_value=rating)})


def _ensure(f: Fetcher, path: Path) -> Path | None:
    """The cached dataset, downloaded when missing or older than MAX_AGE_DAYS. A stale copy beats none."""
    with _download:
        if path.is_file() and time.time() - path.stat().st_mtime <= MAX_AGE_DAYS * 86400:
            return path
        data = f.get_bytes(RATINGS_URL, max_bytes=60_000_000)
        if data is not None and not data.startswith(b"\x1f\x8b"):
            f.warn("imdb: ratings download was not gzip")
            data = None
        if data is not None:
            try:
                _save(path, data)
            except OSError as e:
                f.warn(f"imdb: could not save ratings dataset ({e})")
        if path.is_file():
            return path
        f.warn("imdb: ratings dataset unavailable")
        return None


def _save(path: Path, data: bytes) -> None:
    """Write beside the target and rename, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
