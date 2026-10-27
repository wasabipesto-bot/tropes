from tropes_worker.jobs.find_videos import aott_slugs, is_anime, pick_video, theme_rows, tmdb_titles


def test_theme_rows_label_and_choice():
    anime = {
        "slug": "cyberpunk_edgerunners",
        "animethemes": [
            {
                "type": "OP",
                "sequence": None,
                "slug": "OP1",
                "song": {"title": "This Fffire", "artists": [{"name": "Franz Ferdinand"}]},
                "animethemeentries": [
                    {
                        "videos": [
                            {
                                "link": "https://v.animethemes.moe/A-OP1-NC.webm",
                                "resolution": 1080,
                                "nc": True,
                                "source": "BD",
                                "overlap": "None",
                            },
                            {
                                "link": "https://v.animethemes.moe/A-OP1.webm",
                                "resolution": 720,
                                "nc": False,
                                "source": "WEB",
                                "overlap": "None",
                            },
                        ]
                    }
                ],
            },
            {
                "type": "ED",
                "sequence": 2,
                "slug": "ED2",
                "song": {"title": "Bye", "artists": []},
                "animethemeentries": [
                    {
                        "videos": [
                            {"link": "https://v.animethemes.moe/A-ED2.webm", "resolution": 1080, "nc": True, "overlap": "Over"}
                        ]
                    }
                ],
            },
        ],
    }
    rows = theme_rows(anime, 7)
    assert [r["kind"] for r in rows] == ["opening", "ending"]
    assert rows[0]["label"] == "OP1 · This Fffire — Franz Ferdinand" and rows[0]["url"].endswith("A-OP1.webm")
    assert rows[0]["sourceUrl"] == "https://animethemes.moe/anime/cyberpunk_edgerunners/OP1"
    assert rows[1]["label"] == "ED2 · Bye" and rows[1]["position"] == 102
    assert pick_video([]) is None


def test_is_anime_from_ids_genre_or_folder():
    assert is_anime({"externalIds": {"mal": 1}})
    assert is_anime({"externalIds": {}, "genres": ["Anime", "Drama"]})
    assert is_anime({"externalIds": {}, "genres": [], "localSources": [{"path": "Anime/X (2020)/S01E01.mkv"}]})
    assert not is_anime({"externalIds": {"tmdb_tv": 5}, "genres": ["Drama"], "localSources": [{"path": "TV/X/S01E01.mkv"}]})


def test_aott_slugs_and_tmdb_filter():
    assert aott_slugs("The Fall", 2006) == ["the-fall", "the-fall-2006", "fall"]
    assert aott_slugs("Steins;Gate", None) == ["steins-gate"]
    vids = [
        {"site": "YouTube", "key": "a", "type": "Opening Credits", "name": "Opening Credits"},
        {"site": "YouTube", "key": "b", "type": "Trailer", "name": "Official Trailer"},
        {"site": "YouTube", "key": "c", "type": "Clip", "name": "Title Sequence"},
        {"site": "YouTube", "key": "d", "type": "Clip", "name": "Opening Trailer"},
        {"site": "YouTube", "key": "f", "type": "Clip", "name": "Ceres Opening Scene"},
        {"site": "YouTube", "key": "g", "type": "Clip", "name": "Opening Title (Season 1)"},
        {"site": "Vimeo", "key": "e", "type": "Opening Credits", "name": "x"},
    ]
    assert tmdb_titles(vids) == [("a", "Opening credits"), ("c", "Title Sequence"), ("g", "Opening Title (Season 1)")]
