import httpx

from tropes_worker.cli import main
from tropes_worker.client import SiteClient


def fake_site(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer secret"
    if request.url.path == "/api/health":
        return httpx.Response(200, json={"ok": True, "media": 778, "version": "0.0.0"})
    return httpx.Response(404)


def test_health_parses_response():
    with SiteClient("http://site", "secret", transport=httpx.MockTransport(fake_site)) as c:
        h = c.health()
    assert h.ok and h.media == 778 and h.version == "0.0.0"


def test_ping_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        "tropes_worker.cli.SiteClient",
        lambda site, token: SiteClient(site, "secret", transport=httpx.MockTransport(fake_site)),
    )
    assert main(["--site", "http://site", "ping"]) == 0
    assert "778 media items" in capsys.readouterr().out


def test_site_flag_after_subcommand(monkeypatch):
    seen = {}

    def fake(site, token):
        seen["site"] = site
        return SiteClient(site, "secret", transport=httpx.MockTransport(fake_site))

    monkeypatch.setattr("tropes_worker.cli.SiteClient", fake)
    assert main(["ping", "--site", "http://after"]) == 0
    assert seen["site"] == "http://after"
