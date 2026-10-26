from pathlib import Path

from tropes_worker.jobs.fetch_wiki import fandom_ref, html_to_text
from tropes_worker.pipeline import visual_section, wiki_section
from tropes_worker.sources import Text, blocks_for, text_blocks


def _show(seasons: int, episodes: int, size: int) -> Text:
    chapters = [(f"S{s:02d}E{e:02d} Title {s}-{e}", "x" * size) for s in range(1, seasons + 1) for e in range(1, episodes + 1)]
    full = "\n\n".join(f"## {t}\n{b}" for t, b in chapters)
    return Text(path=Path("show.txt"), source_hash="h", full=full, chapters=chapters)


def test_text_under_the_cap_is_one_block():
    t = _show(1, 3, 100)
    assert text_blocks(t, 10_000) == [t]


def test_long_show_splits_between_seasons_and_packs_them():
    t = _show(4, 5, 1_000)  # 5 k per season, 20 k in all
    blocks = text_blocks(t, 11_000)
    assert [len(b.chapters) for b in blocks] == [10, 10]
    assert blocks[0].chapters[0][0].startswith("S01E01") and blocks[1].chapters[0][0].startswith("S03E01")
    assert blocks[0].path.name.endswith("#block") and "block 1 of 2" in blocks[0].path.stem
    # Quotes still verify: the block is a real Text with the same chapter bodies.
    assert blocks[1].full.startswith("## S03E01")


def test_a_season_over_the_cap_is_cut_into_runs():
    t = _show(1, 6, 1_000)
    blocks = text_blocks(t, 2_500)
    assert [len(b.chapters) for b in blocks] == [2, 2, 2]


def test_blocks_for_reads_the_named_block_and_the_next():
    blocks = text_blocks(_show(4, 5, 1_000), 11_000)
    assert blocks_for(blocks, "The scene in S03E02 where they meet") == [blocks[1]]
    assert blocks_for(blocks, "the opening, S01E01, and later") == blocks
    assert blocks_for(blocks, "nothing named") == [blocks[0], blocks[1]]
    assert blocks_for(blocks, "Title 3-4 is the one") == [blocks[1]]


def test_visual_and_wiki_sections():
    notes = [
        {"source": "visual", "label": "S01E02", "text": "- red coat"},
        {"source": "visual", "label": "S01E01", "text": "- blue hair"},
        {"source": "tumblr", "label": "", "text": "a post"},
        {"source": "wiki", "label": "Fandom", "text": "Plot: things happen."},
    ]
    v = visual_section(notes)
    assert v.startswith("Visual notes") and v.index("S01E01") < v.index("S01E02")
    assert "a post" not in v
    assert visual_section([notes[2]]) == ""
    assert "Fan wiki summary" in wiki_section(notes) and "things happen" in wiki_section(notes)


def test_fandom_ref_parsing():
    assert fandom_ref("arcane:Arcane (TV series)") == ("arcane", "Arcane_(TV_series)")
    assert fandom_ref("de.arcane:Arcane") is None and fandom_ref("pt-br.cyberpunk:Cyberpunk") is None
    assert fandom_ref("nonsense") is None


def test_wiki_html_to_text_keeps_prose_and_drops_boxes():
    html = """<div class="mw-parser-output"><aside class="portable-infobox"><p>Box text</p></aside>
    <p>Arcane is a show.<sup class="reference">[1]</sup></p><h2>Plot</h2><p>Two sisters.</p>
    <table><tr><td>Episode table</td></tr></table><ul><li>Point one</li></ul>
    <h2>References</h2><p>Ref list</p></div>"""
    t = html_to_text(html)
    assert t == "Arcane is a show.\n\nPlot:\nTwo sisters.\nPoint one"
