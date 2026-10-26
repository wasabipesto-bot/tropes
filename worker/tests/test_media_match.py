import sqlite3

from tropes_worker.media.listing import Listing, episode_of, sidecar_subs
from tropes_worker.media.match import best_video, calibre_rows, folder_index, match_book, match_video, parse_folder, title_keys

LISTING = """d\t0\t2024-01-01\tTV/Arcane (2021)
d\t0\t2024-01-01\tTV/Arcane (2021)/Season 01
f\t1000\t2024-01-01\tTV/Arcane (2021)/Season 01/Arcane.S01E01.Welcome.to.the.Playground.1080p.mkv
f\t1000\t2024-01-01\tTV/Arcane (2021)/Season 01/Arcane.S01E02.Some.Mysteries.mkv
f\t10\t2024-01-01\tTV/Arcane (2021)/Season 01/Arcane.S01E02.Some.Mysteries.en.srt
d\t0\t2024-01-01\tTV/Sandman, The
f\t1000\t2024-01-01\tTV/Sandman, The/Season 01/The.Sandman.S01E01.mkv
d\t0\t2024-01-01\tTV/Penny Dreadful X
f\t1000\t2024-01-01\tTV/Penny Dreadful X/Season 01/Penny.Dreadful.S01E01.mkv
d\t0\t2024-01-01\tAnime/Food Wars [Shokugeki no Souma] [2015] [1080p]
f\t1000\t2024-01-01\tAnime/Food Wars [Shokugeki no Souma] [2015] [1080p]/Season 01 (First Plate)/Food Wars - 03.mkv
d\t0\t2024-01-01\tAnime/Mushishi
f\t1000\t2024-01-01\tAnime/Mushishi/Season 01/Mushishi.S01E01.mkv
d\t0\t2024-01-01\tMovies/Children of Men (2006)
f\t9000\t2024-01-01\tMovies/Children of Men (2006)/Children of Men [2006] [1080p].mkv
f\t100\t2024-01-01\tMovies/Children of Men (2006)/Children of Men [2006] [1080p].en.srt
d\t0\t2024-01-01\tMovies/Dune (1984)
f\t9000\t2024-01-01\tMovies/Dune (1984)/Dune.1984.mkv
d\t0\t2024-01-01\tMovies/Dune (2021)
f\t9000\t2024-01-01\tMovies/Dune (2021)/Dune.2021.mkv
d\t0\t2024-01-01\tMovies/Harry Potter 4 - The Goblet of Fire (2005)
f\t9000\t2024-01-01\tMovies/Harry Potter 4 - The Goblet of Fire (2005)/hp4.mkv
d\t0\t2024-01-01\tMovies/Mickey 17 (2024)
f\t9000\t2024-01-01\tMovies/Mickey 17 (2024)/m17.mkv
d\t0\t2024-01-01\tMovies/Much Ado About Nothing (1993)
f\t9000\t2024-01-01\tMovies/Much Ado About Nothing (1993)/a.mkv
d\t0\t2024-01-01\tMovies/Much Ado About Nothing (2012)
f\t9000\t2024-01-01\tMovies/Much Ado About Nothing (2012)/b.mkv
"""


def _folders():
    lst = Listing.from_find(LISTING)
    folders = lst.folders()
    return folders, folder_index(folders)


def test_parse_folder_and_title_keys():
    assert parse_folder("Children of Men (2006)") == ("Children of Men", 2006)
    assert parse_folder("Food Wars [Shokugeki no Souma] [2015] [1080p]") == ("Food Wars", 2015)
    assert parse_folder("Sandman, The") == ("The Sandman", None)
    assert "harry potter goblet fire" in title_keys("Harry Potter and the Goblet of Fire")
    assert "harry potter goblet fire" in title_keys("Harry Potter 4 - The Goblet of Fire")
    assert "mushishi" in title_keys("Mushi-Shi")
    assert episode_of("TV/X/Season 01/X.S01E02.mkv") == (1, 2)
    assert episode_of("Anime/X/Season 01 (First Plate)/Food Wars - 03.mkv") == (1, 3)


def test_video_matching_rules():
    folders, index = _folders()

    def best(title, type_, year):
        return best_video(match_video({"title": title, "type": type_, "year": year}, folders, index))

    arcane, why = best("Arcane", "TV Series", 2021)
    assert why == "ok" and [e[:2] for e in arcane.episodes] == [(1, 1), (1, 2)]
    ep2 = arcane.episodes[1][2]
    assert [s.path for s in sidecar_subs(ep2, arcane.folder.subs)] == [
        "TV/Arcane (2021)/Season 01/Arcane.S01E02.Some.Mysteries.en.srt"
    ]
    assert best("The Sandman", "TV Series", 2022)[1] == "ok"
    assert best("Food Wars!", "TV Series", 2015)[1] == "ok"
    assert best("Mushi-Shi", "TV Series", 2005)[1] == "ok"
    # A near name without a year is offered as a check, not recorded.
    assert best("Penny Dreadful", "TV Series", 2014)[1] == "year"
    # Films: the year in the title decides between remakes; one year off still agrees.
    d84, why = best("Dune (1984)", "Movie", None)
    assert why == "ok" and d84.folder.name == "Dune (1984)"
    assert best("Dune", "Movie", None)[1] == "ambiguous"
    assert best("Harry Potter and the Goblet of Fire", "Movie", 2005)[1] == "ok"
    assert best("Mickey 17", "Movie", 2025)[1] == "ok"
    assert best("Children of Men", "TV Series", 2006)[1] == "none"
    assert best("Much Ado About Nothing", "Movie", None)[1] == "ambiguous"


def _calibre():
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        create table books (id integer primary key, title text, path text);
        create table authors (id integer primary key, name text);
        create table books_authors_link (book integer, author integer);
        create table identifiers (book integer, type text, val text);
        create table data (book integer, format text, name text);
        insert into books values
          (1, 'Gideon the Ninth', 'Tamsyn Muir/Gideon the Ninth (17778)'),
          (2, 'The Time Paradox', 'Eoin Colfer/The Time Paradox (5)'),
          (3, 'Good Omens: The Nice and Accurate Prophecies', 'Terry Pratchett/Good Omens (9)'),
          (4, 'Dune', 'Frank Herbert/Dune (2)');
        insert into authors values
          (1, 'Tamsyn Muir'), (2, 'Eoin Colfer'), (3, 'Terry Pratchett'), (4, 'Neil Gaiman'), (5, 'Frank Herbert');
        insert into books_authors_link values (1, 1), (2, 2), (3, 3), (3, 4), (4, 5);
        insert into identifiers values (1, 'isbn', '9781250313195'), (4, 'goodreads', '234225');
        insert into data values
          (1, 'EPUB', 'Gideon the Ninth - Tamsyn Muir'), (1, 'MOBI', 'Gideon the Ninth - Tamsyn Muir'),
          (2, 'MOBI', 'The Time Paradox - Eoin Colfer'), (3, 'EPUB', 'Good Omens - Terry Pratchett'),
          (4, 'EPUB', 'Dune - Frank Herbert');
        """
    )
    return db


def test_book_matching():
    db = _calibre()
    rows = calibre_rows(db)
    g = match_book({"title": "Gideon the Ninth", "creator": "Tamsyn Muir", "externalIds": {}}, db, rows)
    assert g and g.by == "title+author"
    assert g.file() == "Books/Tamsyn Muir/Gideon the Ninth (17778)/Gideon the Ninth - Tamsyn Muir.epub"
    by_id = match_book({"title": "Dune", "creator": None, "externalIds": {"goodreads": "234225"}}, db, rows)
    assert by_id and by_id.by == "goodreads"
    af = match_book({"title": "Artemis Fowl and the Time Paradox", "creator": "Eoin Colfer", "externalIds": {}}, db, rows)
    assert af and af.title == "The Time Paradox" and af.file().endswith(".mobi")
    go = match_book({"title": "Good Omens", "creator": "Neil Gaiman & Terry Pratchett", "externalIds": {}}, db, rows)
    assert go and go.book_id == 3
    assert match_book({"title": "The Martian", "creator": "Andy Weir", "externalIds": {}}, db, rows) is None
