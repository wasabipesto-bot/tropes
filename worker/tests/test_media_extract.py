import shutil
from pathlib import Path

from tropes_worker.jobs.extract_text import book_text, episode_heading, extract

FIX = Path(__file__).parent / "fixtures"


def test_extract_prefers_an_english_sidecar(tmp_path):
    root = tmp_path
    ep = root / "TV" / "Arcane (2021)" / "Season 01" / "Arcane.S01E01.Welcome.to.the.Playground.1080p.NF.WEB-DL.mkv"
    ep.parent.mkdir(parents=True)
    ep.write_bytes(b"not really video")
    (ep.parent / "Arcane.S01E01.Welcome.to.the.Playground.1080p.NF.WEB-DL.en.srt").write_text(
        (FIX / "subs" / "tv-embedded.srt").read_text()
    )
    (ep.parent / "Arcane.S01E01.Welcome.to.the.Playground.1080p.NF.WEB-DL.fr.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"
    )
    m = {"id": 1, "title": "Arcane", "externalIds": {"imdb": "tt11126994"}}
    s = {
        "id": 10,
        "kind": "video",
        "path": str(ep.relative_to(root)),
        "label": "S01E01",
        "meta": {
            "sidecars": [str(p.relative_to(root)) for p in sorted(ep.parent.glob("*.srt"))],
            "subtitleStreams": [{"index": 2, "codec": "subrip", "lang": "eng"}],
        },
    }
    text, how = extract(root, m, s, None)
    assert how == "sidecar"
    assert text.startswith("## S01E01 Welcome to the Playground\n[4:37] We're almost there.")
    assert episode_heading(m, s, ep) == "S01E01 Welcome to the Playground"
    # A film has no label: the heading is the title.
    assert episode_heading(m, {"label": ""}, ep) == "Arcane"


def test_extract_without_any_subtitle_source(tmp_path):
    root = tmp_path
    f = root / "Movies" / "X (2001)" / "x.mkv"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    text, how = extract(
        root,
        {"id": 2, "title": "X", "externalIds": {}},
        {"id": 11, "kind": "video", "path": str(f.relative_to(root)), "label": "", "meta": {}},
        None,
    )
    assert (text, how) == ("", "none")


def test_book_text_from_epub(tmp_path):
    src = FIX / "sample.epub"
    dst = tmp_path / "Books" / "A" / "B (1)" / "B - A.epub"
    dst.parent.mkdir(parents=True)
    shutil.copy(src, dst)
    text, how = book_text(dst)
    assert how == "epub" and "## " in text and len(text.split()) > 20
