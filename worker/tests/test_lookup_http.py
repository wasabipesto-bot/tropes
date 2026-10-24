import json
import time

import httpx

from tropes_worker.lookup.http import Fetcher


def test_fetcher_caches_and_spaces_requests(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.headers["User-Agent"].startswith("TropeLog/")
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(200, json={"path": request.url.path, "q": request.url.params.get("q")})

    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    first = f.get_json("https://musicbrainz.org/thing", params={"q": "x"})
    assert first == {"path": "/thing", "q": "x"}
    assert f.get_json("https://musicbrainz.org/thing", params={"q": "x"}) == first
    assert calls["n"] == 1 and f.cache_hits == 1
    assert f.get_json("https://musicbrainz.org/missing") is None
    assert f.warnings == []  # 404 is not a warning
    cached = list(tmp_path.rglob("*.json"))
    assert len(cached) == 2 and json.loads(cached[0].read_text())["status"] in (200, 404)

    # The per-host gap applies between uncached requests to one host.
    t0 = time.monotonic()
    f.get_json("https://musicbrainz.org/a", cache=False)
    f.get_json("https://musicbrainz.org/b", cache=False)
    assert time.monotonic() - t0 >= 1.0
    f.close()


def test_fetcher_records_server_errors_as_warnings(tmp_path, monkeypatch):
    monkeypatch.setattr("tropes_worker.lookup.http.time.sleep", lambda s: None)
    f = Fetcher(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert f.get_text("https://example.org/x") is None
    assert any("503" in w for w in f.warnings)
    assert not list(tmp_path.rglob("*.json"))  # failures are not cached
