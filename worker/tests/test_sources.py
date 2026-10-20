from pathlib import Path

from tropes_worker.sources import find_quote, load_text

FIX = Path(__file__).parent / "fixtures"


def test_epub_chapters_and_quote_lookup(tmp_path):
    t = load_text(FIX / "sample.epub", tmp_path)
    assert [c[0] for c in t.chapters] == ["Chapter One", "Chapter Two"]
    assert t.words > 100
    # Straight vs curly apostrophes and whitespace differences do not matter.
    found, chapter = find_quote(t, "Gideon is Harrow's cavalier,  her sworn sword")
    assert found and chapter == "Chapter One"
    assert find_quote(t, "the leash ran both ways, and neither of them could say who was holding it.") == (True, "Chapter Two")
    assert find_quote(t, "this sentence is not in the book at all") == (False, None)
    # Cached on second load.
    assert (tmp_path / f"{t.source_hash}.txt").is_file()


def test_gutenberg_txt_is_stripped_and_chaptered(tmp_path):
    src = tmp_path / "book.txt"
    src.write_text(
        "Header junk\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\nCHAPTER I\n\nIt was a dark night.\n\nCHAPTER II\n\nIt got darker.\n\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\nlicense junk",  # noqa: E501
        encoding="utf-8",
    )
    t = load_text(src, tmp_path / "cache")
    assert "Header junk" not in t.full and "license junk" not in t.full
    assert [c[0] for c in t.chapters] == ["CHAPTER I", "CHAPTER II"]
