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
