import json
from pathlib import Path

import httpx

from tropes_worker.lookup import itunes, musicbrainz, openlibrary, steam
from tropes_worker.lookup.http import Fetcher

FIXTURES = Path(__file__).parent / "fixtures" / "lookup"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _json(data) -> httpx.Response:
    return httpx.Response(200, json=data)


def make_fetcher(tmp_path, handler) -> Fetcher:
    return Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(handler))


# Steam -----------------------------------------------------------------------------------------


def steam_handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "store.steampowered.com" and path == "/api/appdetails":
        return _json(_load("steam-app-control.json"))
    if host == "store.steampowered.com" and path == "/api/storesearch/":
        return _json(_load("steam-search.json"))
    if host.endswith("steamstatic.com"):  # poster existence checks
        return httpx.Response(200)
    return httpx.Response(404)


def test_steam_fetch(tmp_path):
    f = make_fetcher(tmp_path, steam_handler)
    p = steam.fetch(f, {"steam": "870780"}, type_="Game", settings=None)
    assert p is not None
    assert p.details["developer"] == "Remedy Entertainment"
    assert p.details["publisher"] == "Remedy Entertainment"
    assert p.details["start"] == "2020-08-27"
    assert set(p.details["platforms"]) == {"windows", "mac"}
    assert "Action" in p.genres
    assert p.links["steam"].url == "https://store.steampowered.com/app/870780/"
    assert p.links["metacritic"].score == "85"
    assert p.links["metacritic"].score_value == 85
    assert len(p.posters) >= 1
    assert p.ids == {"steam": "870780"}


def test_steam_fetch_no_id(tmp_path):
    f = make_fetcher(tmp_path, steam_handler)
    assert steam.fetch(f, {}, type_="Game", settings=None) is None


def test_steam_search(tmp_path):
    f = make_fetcher(tmp_path, steam_handler)
    cands = steam.search(f, "Control", None, None, type_="Game", settings=None)
    assert len(cands) <= 10
    assert any(c.ids.get("steam") == "870780" and c.label == "CONTROL Ultimate Edition" for c in cands)
    assert all(c.kinds == ["video game"] for c in cands)


def test_steam_date_formats():
    assert steam._parse_release_date("Aug 27, 2020") == "2020-08-27"
    assert steam._parse_release_date("3 Nov, 2019") == "2019-11-03"
    assert steam._parse_release_date("Nov 2019") == "2019-11"
    assert steam._parse_release_date("2019") == "2019"
    assert steam._parse_release_date("") is None
    assert steam._parse_release_date("Coming soon") is None


# Open Library ------------------------------------------------------------------------------------


def openlibrary_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/works/OL20128158W.json":
        return _json(_load("openlibrary-work-gideon.json"))
    if path == "/authors/OL7483937A.json":
        return _json(_load("openlibrary-author-gideon.json"))
    if path == "/search.json":
        return _json(_load("openlibrary-search.json"))
    if path == "/books/OL99999999M.json":  # synthetic edition, not a saved fixture
        return _json({"key": "/books/OL99999999M", "works": [{"key": "/works/OL20128158W"}]})
    if path.startswith("/b/id/"):  # cover image existence
        return httpx.Response(200)
    return httpx.Response(404)


def test_openlibrary_fetch(tmp_path):
    f = make_fetcher(tmp_path, openlibrary_handler)
    p = openlibrary.fetch(f, {"openlibrary": "OL20128158W"}, type_="Book", settings=None)
    assert p is not None
    assert p.details["author"] == "Tamsyn Muir"
    assert p.posters == ["https://covers.openlibrary.org/b/id/10139515-L.jpg"]
    assert len(p.genres) <= 15
    assert p.links["openlibrary"].url == "https://openlibrary.org/works/OL20128158W"
    assert p.ids == {"openlibrary": "OL20128158W"}


def test_openlibrary_fetch_follows_edition_to_work(tmp_path):
    f = make_fetcher(tmp_path, openlibrary_handler)
    p = openlibrary.fetch(f, {"openlibrary": "OL99999999M"}, type_="Book", settings=None)
    assert p is not None
    assert p.details["author"] == "Tamsyn Muir"
    assert p.ids == {"openlibrary": "OL20128158W"}


def test_openlibrary_fetch_no_id(tmp_path):
    f = make_fetcher(tmp_path, openlibrary_handler)
    assert openlibrary.fetch(f, {}, type_="Book", settings=None) is None


def test_openlibrary_search(tmp_path):
    f = make_fetcher(tmp_path, openlibrary_handler)
    cands = openlibrary.search(f, "Gideon the Ninth", "Tamsyn Muir", None, type_="Book", settings=None)
    assert len(cands) <= 10
    assert any(c.ids.get("openlibrary") == "OL20128158W" and c.creator == "Tamsyn Muir" for c in cands)
    assert all(c.kinds == ["literary work"] for c in cands)


# MusicBrainz -------------------------------------------------------------------------------------

MBID = "b1392450-e666-3926-a536-22c65f834433"
RELEASE_ID = "1834eae1-741b-3c03-9ca5-0df3decb43ea"


def musicbrainz_handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "musicbrainz.org" and path == f"/ws/2/release-group/{MBID}":
        return _json(_load("musicbrainz-rg-ok-computer.json"))
    if host == "musicbrainz.org" and path == f"/ws/2/release/{RELEASE_ID}":
        return _json(_load("musicbrainz-release-ok-computer.json"))
    if host == "musicbrainz.org" and path == "/ws/2/release-group":
        return _json(_load("musicbrainz-search.json"))
    if host == "coverartarchive.org":
        return httpx.Response(200)
    return httpx.Response(404)


def test_musicbrainz_fetch(tmp_path):
    f = make_fetcher(tmp_path, musicbrainz_handler)
    p = musicbrainz.fetch(f, {"musicbrainz_rg": MBID}, type_="Album", settings=None)
    assert p is not None
    assert p.details["artist"] == "Radiohead"
    assert p.details["start"] == "1997-05-21"
    assert p.details["tracks"] == 12
    assert len(p.genres) <= 10
    assert p.posters == [f"https://coverartarchive.org/release-group/{MBID}/front-500"]
    assert p.links["musicbrainz"].url == f"https://musicbrainz.org/release-group/{MBID}"
    assert p.ids == {"musicbrainz_rg": MBID}


def test_musicbrainz_fetch_no_id(tmp_path):
    f = make_fetcher(tmp_path, musicbrainz_handler)
    assert musicbrainz.fetch(f, {}, type_="Album", settings=None) is None


def test_musicbrainz_search(tmp_path):
    f = make_fetcher(tmp_path, musicbrainz_handler)
    cands = musicbrainz.search(f, "OK Computer", "Radiohead", None, type_="Album", settings=None)
    assert len(cands) <= 10
    assert any(c.ids.get("musicbrainz_rg") == MBID and c.creator == "Radiohead" and c.year == 1997 for c in cands)
    assert all(c.kinds == ["album"] for c in cands)


# iTunes --------------------------------------------------------------------------------------------

PODCAST_ID = "811377230"
ALBUM_ID = "1097861387"


def itunes_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/lookup":
        tid = request.url.params.get("id")
        if tid == PODCAST_ID:
            return _json(_load("itunes-lookup-podcast.json"))
        if tid == ALBUM_ID:
            return _json(_load("itunes-lookup-album.json"))
        return httpx.Response(404)
    if path == "/search":
        entity = request.url.params.get("entity")
        search_fixture = _load("itunes-search.json")
        if entity == "podcast":
            return _json(search_fixture["podcast"])
        if entity == "album":
            return _json(search_fixture["album"])
        return httpx.Response(404)
    return httpx.Response(404)


def test_itunes_fetch_podcast(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    p = itunes.fetch(f, {"itunes": PODCAST_ID}, type_="Podcast", settings=None)
    assert p is not None
    assert p.details["episodes"] == 100
    assert p.details["network"] == "CGP Grey & Brady Haran"
    assert "start" not in p.details
    assert p.posters[0].endswith("/1200x1200bb.jpg")
    assert p.links["itunes"].url.startswith("https://podcasts.apple.com/")
    assert p.ids == {"itunes": PODCAST_ID}


def test_itunes_fetch_album(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    p = itunes.fetch(f, {"itunes": ALBUM_ID}, type_="Album", settings=None)
    assert p is not None
    assert p.details["artist"] == "Radiohead"
    assert p.details["start"] == "1997-05-21"
    assert p.details["tracks"] == 12
    assert p.genres == ["Alternative"]
    assert p.posters[0].endswith("/1200x1200bb.jpg")


def test_itunes_fetch_no_id(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    assert itunes.fetch(f, {}, type_="Podcast", settings=None) is None


def test_itunes_search_podcast(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    cands = itunes.search(f, "Hello Internet", None, None, type_="Podcast", settings=None)
    assert len(cands) <= 10
    assert any(c.ids.get("itunes") == PODCAST_ID and c.creator == "CGP Grey & Brady Haran" for c in cands)
    assert all(c.kinds == ["podcast"] for c in cands)


def test_itunes_search_album(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    cands = itunes.search(f, "OK Computer", "Radiohead", None, type_="Album", settings=None)
    assert len(cands) <= 10
    assert any(c.ids.get("itunes") == ALBUM_ID and c.year == 1997 for c in cands)
    assert all(c.kinds == ["album"] for c in cands)


def test_itunes_search_other_type_is_empty(tmp_path):
    f = make_fetcher(tmp_path, itunes_handler)
    assert itunes.search(f, "Anything", None, None, type_="Movie", settings=None) == []
