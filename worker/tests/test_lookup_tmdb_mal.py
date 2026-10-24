import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from tropes_worker.lookup import mal, tmdb
from tropes_worker.lookup.http import Fetcher

FIXTURES = Path(__file__).parent / "fixtures" / "lookup"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@dataclass
class FakeSettings:
    tmdb_token: str | None = "test-tmdb-token"
    mal_client_id: str | None = "test-mal-client-id"


def transport(routes: dict[str, object], *, expect_header: tuple[str, str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if expect_header:
            k, v = expect_header
            assert request.headers[k] == v
        body = routes.get(request.url.path)
        return httpx.Response(404) if body is None else httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


# TMDB fetch --------------------------------------------------------------------------------------


def test_tmdb_fetch_tv_pantheon(tmp_path):
    routes = {"/3/tv/195339": load("tmdb-tv-pantheon.json")}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes, expect_header=("Authorization", "Bearer test-tmdb-token")))
    p = tmdb.fetch(f, {"tmdb_tv": "195339"}, type_="TV Series", settings=FakeSettings())
    assert p is not None
    assert p.details == {
        "start": "2022-09-01",
        "end": "2025-02-21",
        "seasons": 2,
        "episodes": 16,
        "network": "Netflix",
        "status": "Canceled",
    }
    assert p.genres == ["Animation", "Sci-Fi & Fantasy"]
    assert p.ids == {"imdb": "tt11680642", "tvdb": "417208"}
    assert p.posters[0] == "https://image.tmdb.org/t/p/original/28xQt18ryWRcx9tBkK0MBsNNRw5.jpg"
    assert len(p.posters) == 13  # main + up to 12 more
    assert p.links["tmdb"].url == "https://www.themoviedb.org/tv/195339"
    assert p.warnings == []


def test_tmdb_fetch_movie_dune(tmp_path):
    routes = {"/3/movie/438631": load("tmdb-movie-dune.json")}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    p = tmdb.fetch(f, {"tmdb_movie": "438631"}, type_="Movie", settings=FakeSettings())
    assert p is not None
    assert p.details["start"] == "2021-09-15"
    assert p.details["runtime_min"] == 155
    assert p.details["studio"] == "Legendary Pictures"
    assert p.details["director"] == "Denis Villeneuve"
    assert p.genres == ["Science Fiction", "Adventure"]
    assert p.ids == {"imdb": "tt1160419"}
    assert p.links["tmdb"].url == "https://www.themoviedb.org/movie/438631"


def test_tmdb_fetch_resolves_via_imdb_find(tmp_path):
    routes = {
        "/3/find/tt11680642": load("tmdb-find.json"),
        "/3/tv/195339": load("tmdb-tv-pantheon.json"),
    }
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    p = tmdb.fetch(f, {"imdb": "tt11680642"}, type_="TV Series", settings=FakeSettings())
    assert p is not None
    assert p.ids["tmdb_tv"] == "195339"  # discovered id surfaces in Partial.ids
    assert p.ids["imdb"] == "tt11680642"
    assert p.details["seasons"] == 2


def test_tmdb_fetch_no_token(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    p = tmdb.fetch(f, {"tmdb_tv": "195339"}, type_="TV Series", settings=FakeSettings(tmdb_token=None))
    assert p == type(p)(warnings=["TMDB: no TROPES_TMDB_TOKEN, skipped"])


def test_tmdb_fetch_no_id_available(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert tmdb.fetch(f, {}, type_="TV Series", settings=FakeSettings()) is None


def test_tmdb_fetch_find_miss_returns_none(tmp_path):
    routes = {"/3/find/tt0000000": {"tv_results": [], "movie_results": [], "person_results": []}}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    assert tmdb.fetch(f, {"imdb": "tt0000000"}, type_="TV Series", settings=FakeSettings()) is None


# TMDB search ---------------------------------------------------------------------------------------


def test_tmdb_search_tv_only(tmp_path):
    fixture = load("tmdb-search.json")
    routes = {"/3/search/tv": fixture["tv"]}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    cands = tmdb.search(f, "Pantheon", None, type_="TV Series", settings=FakeSettings())
    assert len(cands) == len(fixture["tv"]["results"])
    assert all(c.source == "tmdb" and c.kinds == ["television series"] for c in cands)
    assert cands[0].ids == {"tmdb_tv": str(fixture["tv"]["results"][0]["id"])}
    assert cands[0].label == fixture["tv"]["results"][0]["name"]


def test_tmdb_search_movie_only(tmp_path):
    fixture = load("tmdb-search.json")
    routes = {"/3/search/movie": fixture["movie"]}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    cands = tmdb.search(f, "Dune", None, type_="Movie", settings=FakeSettings())
    assert len(cands) == len(fixture["movie"]["results"])
    assert all(c.source == "tmdb" and c.kinds == ["film"] for c in cands)
    assert cands[0].ids == {"tmdb_movie": str(fixture["movie"]["results"][0]["id"])}


def test_tmdb_search_other_type_tries_both(tmp_path):
    fixture = load("tmdb-search.json")
    routes = {"/3/search/tv": fixture["tv"], "/3/search/movie": fixture["movie"]}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    cands = tmdb.search(f, "whatever", None, type_="Anime", settings=FakeSettings())
    assert len(cands) == len(fixture["tv"]["results"]) + len(fixture["movie"]["results"])


def test_tmdb_search_no_token(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert tmdb.search(f, "x", None, type_="TV Series", settings=FakeSettings(tmdb_token=None)) == []


# MAL fetch -----------------------------------------------------------------------------------------


def test_mal_fetch_metallic_rouge(tmp_path):
    routes = {"/v2/anime/54794": load("mal-anime-metallic-rouge.json")}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes, expect_header=("X-MAL-CLIENT-ID", "test-mal-client-id")))
    p = mal.fetch(f, {"mal": "54794"}, type_="TV Series", settings=FakeSettings())
    assert p is not None
    assert p.details == {
        "start": "2024-01-11",
        "end": "2024-04-04",
        "episodes": 13,
        "studio": "Bones",
        "source_material": "original",
        "status": "finished_airing",
    }
    assert set(p.genres) == {"Action", "Sci-Fi"}
    assert p.posters == ["https://cdn.myanimelist.net/images/anime/1859/140210l.jpg"]
    link = p.links["mal"]
    assert link.url == "https://myanimelist.net/anime/54794"
    assert link.score == "6.21"
    assert link.score_value == 6.21


def test_mal_fetch_no_client_id(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    p = mal.fetch(f, {"mal": "54794"}, type_="TV Series", settings=FakeSettings(mal_client_id=None))
    assert p == type(p)(warnings=["MAL: no TROPES_MAL_CLIENT_ID, skipped"])


def test_mal_fetch_no_id(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert mal.fetch(f, {}, type_="TV Series", settings=FakeSettings()) is None


# MAL search ------------------------------------------------------------------------------------------


def test_mal_search(tmp_path):
    fixture = load("mal-search.json")
    routes = {"/v2/anime": fixture}
    f = Fetcher(cache_dir=tmp_path, transport=transport(routes))
    cands = mal.search(f, "Metallic Rouge", None, type_="TV Series", settings=FakeSettings())
    assert len(cands) == 1
    c = cands[0]
    assert c.label == "Metallic Rouge"
    assert c.ids == {"mal": "54794"}
    assert c.source == "mal"
    assert c.kinds == ["anime television series"]
    assert c.year == 2024


def test_mal_search_no_client_id(tmp_path):
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert mal.search(f, "x", None, type_="TV Series", settings=FakeSettings(mal_client_id=None)) == []
