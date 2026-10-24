from tropes_worker.notion import row_from_page


def page(**props):
    base = {
        "Title": {"type": "title", "title": [{"plain_text": "Control "}, {"plain_text": "Resonant"}]},
        "Type": {"type": "select", "select": {"name": "Game"}},
        "Artist/Developer": {"type": "rich_text", "rich_text": [{"plain_text": "Remedy"}]},
        "Medium": {"type": "number", "number": None},
        "Story": {"type": "number", "number": 4.5},
        "Tone": {"type": "number", "number": None},
        "Enjoyability": {"type": "number", "number": None},
        "Effect": {"type": "number", "number": None},
        "Date": {"type": "date", "date": {"start": "2026-10-23", "end": None}},
        "Image Link": {"type": "url", "url": None},
        "Media Link": {"type": "url", "url": "https://store.steampowered.com/app/1/"},
    }
    base.update(props)
    return {"id": "40310d2c-c6e3-80c6-a3e8-cd32b98b8fde", "properties": base}


def test_row_from_page_maps_the_log_fields():
    row = row_from_page(page())
    assert row == {
        "notionId": "40310d2cc6e380c6a3e8cd32b98b8fde",
        "title": "Control Resonant",
        "type": "Game",
        "creator": "Remedy",
        "loggedDate": "2026-10-23",
        "ratings": {"medium": None, "story": 4.5, "tone": None, "enjoyability": None, "effect": None},
        "imageUrl": None,
        "mediaUrl": "https://store.steampowered.com/app/1/",
    }


def test_row_without_title_or_type_is_dropped():
    assert row_from_page(page(**{"Title": {"type": "title", "title": []}})) is None
    assert row_from_page(page(**{"Type": {"type": "select", "select": None}})) is None
    undated = row_from_page(page(**{"Date": {"type": "date", "date": None}}))
    assert undated and undated["loggedDate"] is None
