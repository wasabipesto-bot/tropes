import json

from pydantic import ValidationError

from tropes_worker.llm import _extract_json, load_prompt, render
from tropes_worker.schemas import DossierOut, Pass1Out, Pass2Out
from tropes_worker.writing_check import complaints


def test_prompt_files_render_with_version():
    assert load_prompt("pass1").version >= 1
    out = render("rewrite", {"complaints": "- x", "text": "hello"})
    assert "- x" in out and "hello" in out and "{{" not in out


def test_json_extraction_and_validation():
    raw = 'Sure:\n```json\n{"items": [{"subject": "media:1", "score": 0.7, "reason": "ok"}]}\n```'
    out = Pass1Out.model_validate_json(_extract_json(raw))
    assert out.items[0].score == 0.7
    try:
        Pass2Out.model_validate_json(json.dumps({"match": True, "score": 1.5}))
    except ValidationError:
        pass
    else:
        raise AssertionError("score above 1 should fail")
    d = DossierOut.model_validate_json(json.dumps({"known": "none", "summary": "x"}))
    assert d.characters == []


def test_writing_check_catches_tells():
    assert complaints("A reminder that the model found this.")
    assert "unbalanced" in " ".join(complaints("Gideon ||dies so Harrow"))
    assert complaints("Ned brings the dead back with a touch, and a second touch sends them back for good.") == []


def test_blurb_non_answers_are_not_descriptions():
    from tropes_worker.jobs.write_blurbs import usable

    assert not usable("A Remedy game logged for 2026. I do not know this title, so I cannot describe its premise.")
    assert not usable("Short.")
    assert usable("An animated gothic action series based on the Konami games, following Trevor Belmont as he fights Dracula.")


def test_extract_feeds_only_weakly_known_dossiers():
    from tropes_worker.pipeline import dossier_needed, extract_hash, wants_extract

    strong = {"wikiExtract": "x", "dossier": {"known": "strong", "promptVersion": 2, "depth": "knowledge", "sourceHash": None}}
    partial = {"wikiExtract": "x", "dossier": {"known": "partial", "promptVersion": 2, "depth": "knowledge", "sourceHash": None}}
    assert not wants_extract(strong) and wants_extract(partial)
    assert not dossier_needed(strong, 2, False, None)
    assert dossier_needed(partial, 2, False, None)
    partial["dossier"]["sourceHash"] = extract_hash(partial)
    assert not dossier_needed(partial, 2, False, None)


def test_wikimedia_thumbnails_fetch_the_original():
    from tropes_worker.lookup.posters import fetch_url

    thumb = "https://upload.wikimedia.org/wikipedia/en/thumb/e/e5/Control_game_cover_art.jpg/220px-Control_game_cover_art.jpg"
    assert fetch_url(thumb) == "https://upload.wikimedia.org/wikipedia/en/e/e5/Control_game_cover_art.jpg"
    full = "https://upload.wikimedia.org/wikipedia/en/0/01/IainMBanksExcession.jpg"
    assert fetch_url(full) == full
    assert fetch_url("https://theposterdb.com/api/assets/263743") == "https://theposterdb.com/api/assets/263743"


def test_quotes_from_subtitle_text_carry_timestamps(tmp_path):
    from tropes_worker.pipeline import verify_quotes
    from tropes_worker.schemas import QuoteOut
    from tropes_worker.sources import load_text

    src = tmp_path / "show.txt"
    src.write_text(
        "## S01E01 Welcome\n[0:01] We're almost there.\n[12:40] You think my head is thick?\n\n"
        "## S01E02 Next\n[3:05] Hello there, old friend.\n"
    )
    text = load_text(src, tmp_path / "cache")
    kept, dropped = verify_quotes(
        text,
        [
            QuoteOut(content="You think my head is thick?"),
            QuoteOut(content="Hello there, old friend."),
            QuoteOut(content="Not in the text at all."),
        ],
    )
    assert dropped == 1
    assert kept[0] == {"kind": "quote", "content": "You think my head is thick?", "locator": "S01E01 12:40", "at": 760}
    assert kept[1]["locator"] == "S01E02 3:05" and kept[1]["at"] == 185
