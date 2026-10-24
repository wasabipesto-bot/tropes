import gzip
import os
import re
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tropes_worker.lookup import imdb, scores
from tropes_worker.lookup.http import Fetcher
from tropes_worker.lookup.models import Link

FIX = Path(__file__).parent / "fixtures" / "lookup"
DAY = 86400


@pytest.fixture(autouse=True)
def no_host_gap(monkeypatch):
    monkeypatch.setattr("tropes_worker.lookup.http.time.sleep", lambda s: None)


def _fetcher(tmp_path, pages: dict[str, str | bytes]):
    """A Fetcher whose network is `pages` (url path -> body); everything else is a 404. Returns (fetcher, requests)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = pages.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body if isinstance(body, bytes) else body.encode())

    return Fetcher(cache_dir=tmp_path / "http", transport=httpx.MockTransport(handler)), seen


def _drop_scripts(html: str, attr: str) -> str:
    return re.sub(rf"<script\b[^>]*{re.escape(attr)}[^>]*>.*?</script>", "", html, flags=re.S)


# Page readers ---------------------------------------------------------------------------------------


def test_rotten_tomatoes_reads_the_critics_score(tmp_path):
    page = (FIX / "rt-pantheon.html").read_text()
    card, ld = _drop_scripts(page, "ld+json"), _drop_scripts(page, "media-scorecard-json")
    f, seen = _fetcher(tmp_path, {"/tv/pantheon": page, "/tv/card": card, "/tv/ld": ld})
    url = "https://www.rottentomatoes.com/tv/pantheon"
    assert scores.rotten_tomatoes(f, "tv/pantheon") == Link(url=url, score="100%", score_value=100.0)
    assert seen[0].headers["Accept"] == "text/html" and seen[0].headers["User-Agent"].startswith("TropeLog/")
    # Either block alone answers: the scorecard (picked by id among the page's JSON blocks), or the JSON-LD Tomatometer.
    assert scores.rotten_tomatoes(f, "tv/card").score == "100%"
    assert scores.rotten_tomatoes(f, "/tv/ld/").score == "100%"


def test_metacritic_reads_the_metascore(tmp_path):
    f, seen = _fetcher(tmp_path, {"/tv/pantheon/": (FIX / "metacritic-pantheon.html").read_text()})
    url = "https://www.metacritic.com/tv/pantheon/"
    assert scores.metacritic(f, "tv/pantheon") == Link(url=url, score="77", score_value=77.0)
    assert [r.url.path for r in seen] == ["/tv/pantheon/"]  # asked at the canonical URL, so no redirect hop


def test_goodreads_reads_the_average_rating(tmp_path):
    f, _ = _fetcher(tmp_path, {"/book/show/42036538": (FIX / "goodreads-gideon.html").read_text()})
    url = "https://www.goodreads.com/book/show/42036538"
    assert scores.goodreads(f, "42036538") == Link(url=url, score="4.17", score_value=4.17)


def test_readers_return_none_without_the_block_or_the_page(tmp_path):
    rt = _drop_scripts(_drop_scripts((FIX / "rt-pantheon.html").read_text(), "media-scorecard-json"), "ld+json")
    mc = _drop_scripts((FIX / "metacritic-pantheon.html").read_text(), "ld+json")
    gr_page = (FIX / "goodreads-gideon.html").read_text()
    gr = _drop_scripts(gr_page, "ld+json")
    unscored = gr_page.replace('"ratingValue":4.17,"ratingCount":199700', '"ratingValue":0,"ratingCount":0')
    junk = '<script id="media-scorecard-json" type="application/json">{"criticsScore": {"score": </script>'
    pages = {"/tv/pantheon": rt, "/tv/pantheon/": mc, "/book/show/1": gr, "/book/show/2": unscored, "/m/junk": junk}
    f, seen = _fetcher(tmp_path, pages)
    assert scores.rotten_tomatoes(f, "tv/pantheon") is None
    assert scores.metacritic(f, "tv/pantheon") is None
    assert scores.goodreads(f, "1") is None
    assert scores.goodreads(f, "2") is None
    assert scores.rotten_tomatoes(f, "m/junk") is None
    assert scores.metacritic(f, "game/missing") is None  # 404
    n = len(seen)
    # Not a plain path: never requested (search pages are disallowed by robots.txt).
    assert scores.metacritic(f, "search/pantheon") is None
    assert scores.rotten_tomatoes(f, "m/../search?q=pantheon") is None
    assert scores.goodreads(f, "42036538/reviews") is None
    assert len(seen) == n and f.warnings == []


# IMDb dataset ---------------------------------------------------------------------------------------


def _cached(tmp_path, age_days: float = 0) -> SimpleNamespace:
    settings = SimpleNamespace(lookup_cache_dir=tmp_path / "lookup")
    path = imdb.dataset_path(settings)
    path.parent.mkdir(parents=True)
    shutil.copy(FIX / "imdb-ratings-sample.tsv.gz", path)
    then = time.time() - age_days * DAY
    os.utime(path, (then, then))
    return settings


def _dataset(rows: str) -> bytes:
    return gzip.compress(f"tconst\taverageRating\tnumVotes\n{rows}".encode())


def test_ratings_for_reads_only_requested_ids_from_a_fresh_cache(tmp_path):
    settings = _cached(tmp_path, age_days=29)
    f, seen = _fetcher(tmp_path, {})
    got = imdb.ratings_for(f, settings, {"tt11680642", "tt1168064", "tt15239678", "tt9999999"})
    assert got == {"tt11680642": (8.5, 24346), "tt1168064": (7.8, 437), "tt15239678": (8.4, 801207)}
    assert imdb.ratings_for(f, settings, set()) == {}
    assert seen == []  # fresh file reused, nothing downloaded


def test_ratings_for_redownloads_a_stale_file(tmp_path):
    settings = _cached(tmp_path, age_days=31)
    f, seen = _fetcher(tmp_path, {"/title.ratings.tsv.gz": _dataset("tt11680642\t8.6\t25000\n")})
    assert imdb.ratings_for(f, settings, {"tt11680642", "tt0133093"}) == {"tt11680642": (8.6, 25000)}
    assert [str(r.url) for r in seen] == [imdb.RATINGS_URL]
    assert time.time() - imdb.dataset_path(settings).stat().st_mtime < 60
    # Now fresh: the next call reads the new file without fetching.
    assert imdb.ratings_for(f, settings, {"tt11680642"}) == {"tt11680642": (8.6, 25000)}
    assert len(seen) == 1


def test_ratings_for_without_dataset_warns_and_keeps_a_stale_copy(tmp_path):
    f, _ = _fetcher(tmp_path, {})
    empty = SimpleNamespace(lookup_cache_dir=tmp_path / "none")
    assert imdb.ratings_for(f, empty, {"tt11680642"}) == {}
    assert any("imdb" in w for w in f.warnings)
    # A failed refresh falls back to the stale file.
    assert imdb.ratings_for(f, _cached(tmp_path, age_days=90), {"tt11680642"}) == {"tt11680642": (8.5, 24346)}


def test_imdb_fetch_builds_the_scored_link(tmp_path):
    settings = _cached(tmp_path)
    f, seen = _fetcher(tmp_path, {})
    p = imdb.fetch(f, {"imdb": "tt11680642"}, type_="tv", settings=settings, ratings={"tt11680642": (8.5, 24346)})
    assert p.links == {"imdb": Link(url="https://www.imdb.com/title/tt11680642/", score="8.5", score_value=8.5)}
    # Without a ratings dict it scans the cached dataset for this one id.
    assert imdb.fetch(f, {"imdb": "tt15239678"}, type_="movie", settings=settings).links["imdb"].score == "8.4"
    # Under the vote floor: the link, no score.
    unrated = imdb.fetch(f, {"imdb": "tt9999999"}, type_="tv", settings=settings, ratings={})
    assert unrated.links == {"imdb": Link(url="https://www.imdb.com/title/tt9999999/")}
    assert imdb.fetch(f, {"tmdb_tv": "1"}, type_="tv", settings=settings) is None
    assert seen == []
