from pathlib import Path

import httpx

from tropes_worker.media.opensubtitles import OpenSubtitles
from tropes_worker.media.subtitles import clean, is_english, parse, parse_stamp, render, stamp

FIX = Path(__file__).parent / "fixtures" / "subs"


def test_parse_and_clean_real_files():
    tv = parse((FIX / "tv-embedded.srt").read_text(encoding="utf-8"))
    assert len(tv) > 300 and tv[0].text == "We're almost there." and abs(tv[0].start - 277.583) < 0.01
    movie = parse((FIX / "movie-external.srt").read_text(encoding="utf-8", errors="replace"))
    assert movie and movie[0].text.startswith("We're all familiar")
    assert is_english(tv) and is_english(movie)
    assert clean("<i>[door slams]</i> - JAYCE: Hello\\N- (sighs) there ♪") == "Hello there"
    assert clean("{\\an8}Text on screen") == "Text on screen"
    assert parse("not a subtitle file at all") == []


def test_render_joins_sentences_and_stamps():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nWe're almost\n\n2\n00:00:02,200 --> 00:00:03,000\nthere.\n\n"
    srt += "3\n00:01:05,000 --> 00:01:06,000\nGo!\n"
    cues = parse(srt)
    text = render(cues, "S01E01 Welcome")
    assert text == "## S01E01 Welcome\n[0:01] We're almost there.\n[1:05] Go!"
    assert (
        stamp(3725) == "1:02:05" and parse_stamp("1:02:05") == 3725 and parse_stamp("12:40") == 760 and parse_stamp("x") is None
    )


def test_opensubtitles_search_and_download(monkeypatch):
    monkeypatch.setattr("tropes_worker.media.opensubtitles.time.sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["Api-Key"] == "k"
        if request.url.path == "/api/v1/login":
            return httpx.Response(200, json={"token": "jwt"})
        if request.url.path == "/api/v1/subtitles":
            assert request.url.params["imdb_id"] == "11680642" and request.url.params["season_number"] == "1"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "attributes": {
                                "hearing_impaired": True,
                                "from_trusted": True,
                                "download_count": 900,
                                "files": [{"file_id": 1, "file_name": "sdh.srt"}],
                            }
                        },
                        {
                            "attributes": {
                                "hearing_impaired": False,
                                "from_trusted": False,
                                "download_count": 500,
                                "files": [{"file_id": 2, "file_name": "plain.srt"}],
                            }
                        },
                    ]
                },
            )
        if request.url.path == "/api/v1/download":
            assert request.headers["Authorization"] == "Bearer jwt"
            return httpx.Response(200, json={"link": "https://dl.example/2.srt", "remaining": 19})
        if request.url.host == "dl.example":
            return httpx.Response(200, text="1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        return httpx.Response(404)

    os = OpenSubtitles("k", user="u", password="p", transport=httpx.MockTransport(handler))
    assert os.login()
    text = os.fetch("tt11680642", season=1, episode=3)
    assert text and "Hi" in text and os.remaining == 19
    assert [r.url.path for r in calls][:3] == ["/api/v1/login", "/api/v1/subtitles", "/api/v1/download"]
    # The plain file was preferred over the hearing-impaired one despite fewer downloads.
    assert (
        calls[2].read() == b'{"file_id":2,"sub_format":"srt"}'
        or b'"file_id": 2' in calls[2].read()
        or b'"file_id":2' in calls[2].read()
    )
