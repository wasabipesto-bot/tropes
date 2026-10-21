# Phase 4 plan: external metadata and posters

Written 2026-10-21 for approval before any of it is built. Same shape as
`phase-3.md`: tasks, each with scope, approach, the decisions it needs (with
a recommendation), implementation detail and tradeoffs. The bias is the
same: the fewest moving parts that do the job. No new services, no new
queue, no client framework; the worker gains one job kind and a handful of
small per-site fetchers, the site gains three tables and two pages.

What Phase 4 delivers: every log entry that exists somewhere public gets a
confirmed identity, a populated metadata line, a links line with scores, a
locally stored poster and genres; the library gains a genre filter; Add
media gains its real step 2 ("confirm what was found").

Section 3 lists what was probed from ivory on 2026-10-21, so the
recommendations below rest on things that were seen to work.

---

## 0. Shape of the system after Phase 4

```
site (Astro, SQLite)                        worker (Python, ivory)
  media + media_link + media_genre     <──  lookup_media job: resolve identity,
  posters stored under data/posters          fetch details, scores, poster, genres
  /metadata review page, add-media step 2    per-host polite fetchers, raw-response cache
                                             model used only to disambiguate and to map genres
```

Unchanged rules: the worker never opens the database, the site never calls
the model or any outside site, nothing is saved until the owner commits.
New for this phase: the site never hotlinks a poster.

---

## 1. Tasks

| # | Task | Size | Depends on |
|---|---|---|---|
| T1 | Schema: identity, details, links, genres, posters | S | |
| T2 | Identity resolution | M | T1 |
| T3 | Fetchers: details, links and scores per site | M | T2 |
| T4 | Posters | S | T1 |
| T5 | Genres and the library filter | S | T3 |
| T6 | Media page: metadata line, links line, owner corrections | S | T1, T3 |
| T7 | Backfill and its review page | M | T2–T5 |
| T8 | Add media, step 2 | M | T2–T5, Phase 3 check_subject |
| T9 | Notion sync through the API (optional, see D19) | S | |
| T10 | Operations: keys, refresh, tests, docs | S | all |

---

## T1. Schema

**Scope.** One migration (`0005_metadata`) that gives each media row a
pinned identity and somewhere to put what the lookup finds.

**Tables.**

```
media (new columns)
  wikidata_id      text      the pinned identity, null until confirmed; "none" = owner said no match
  external_ids     JSON      {imdb, tmdb_tv|tmdb_movie, tvdb, mal, steam, openlibrary, musicbrainz_rg, itunes, …}
  details          JSON      per type: start, end, seasons, episodes, runtime_min, studio, network,
                             source_material, developer, publisher, platforms, tracks, pages?
  poster_source    text      URL the stored poster came from (re-fetch when it changes)
  metadata_at      text      when details/links/scores were last refreshed

media_link   id, media_id, site, url, score (display text: "77", "100%", "6.21"),
             score_value real, origin (lookup|notion|owner), hidden bool, fetched_at
             unique (media_id, site)
media_genre  media_id, genre   primary key both; genre from the vocabulary in T5
```

`poster_path` already exists and now points at a local file. `details` is
JSON for the same reason job payloads are (Phase 3 D4): the fields differ
by type and a column per field means a migration per source. Genres get a
real table because the library filters on them.

**Ownership.** Notion still owns title, type, creator, ratings, date,
Image Link and Media Link; a re-import never touches the new columns. The
lookup owns `details`, `external_ids` and `origin='lookup'` links; a
refresh overwrites those. The owner owns `origin='owner'` links, the
`hidden` flag, genres once edited, and the pinned `wikidata_id`; nothing
automatic overwrites them.

**Decisions.**

- **D1. Identity is pinned once confirmed.** A refresh re-fetches from the
  pinned ids and never re-matches; "Wrong match" on the media page is the
  only way to change it. Recommendation: yes. Matching is the error-prone
  step; doing it once, with the owner looking, and never again keeps a
  monthly refresh boring.

**Acceptance.** Migration applies on a copy of the dev database; a Notion
re-import leaves the new columns alone (test).

---

## T2. Identity resolution

**Scope.** Given a log entry (title, type, creator, Notion Media Link,
logged date), find the one public thing it refers to, or say there is
none.

**Approach.** Wikidata is the hub. One Wikidata item carries the IMDb,
TMDB, TVDB, MAL, AniDB, ANN, Rotten Tomatoes, Metacritic, Goodreads, Steam,
Letterboxd, MusicBrainz and Open Library ids plus the English Wikipedia
article, so resolving to a Wikidata id once replaces a fuzzy search on
every site. Pantheon resolved this way returned IMDb, TMDB, TVDB, Rotten
Tomatoes and Metacritic ids, the official site, seasons, episodes and
network from one request (section 3).

1. **Exact seeds first.** The Notion Media Link carries an id for 203
   entries: IMDb (78), Steam (67), Spotify (34), Goodreads (24). Each maps
   to a Wikidata property (`haswbstatement:P345=tt…`, `P1733`, `P2205`,
   `P2969`), which is an exact lookup. One Spotify link is shared by nine
   unrelated albums in Notion (the placeholder noted on 2026-10-19), so a
   link that appears on more than one entry is not used as a seed (that
   leaves 194).
2. **Search otherwise.** Wikidata full-text search on the title, top ten
   results, each fetched with its claims. Candidates are scored on: label
   or alias equal to the normalised title; instance-of in the expected
   class family for the type (film, television series, literary work or
   novel, video game, album, podcast); creator match (director, author,
   developer, performer, network or studio labels against Notion's
   Artist/Developer); release year not after the logged year.
3. **Per-site search as fallback** for things Wikidata lacks: TMDB search
   for films and TV, Steam store search for games, Open Library for books,
   MusicBrainz for albums, iTunes for podcasts. A hit there still gives a
   usable identity (`wikidata_id` stays null, `external_ids` carries the
   site id).
4. **The model only when it is ambiguous.** If the top candidate wins
   clearly (exact seed, or exact title plus type plus creator), it is
   confident. If two or more are close, one model call gets the log entry
   and up to five candidates (label, description, year, creator, Wikipedia
   first sentence) and returns a choice or "none" with a confidence.
   Everything else is "not found".

Output per entry: `confident | check | not_found`, the chosen candidate,
and the runners-up (kept so "Wrong match" can offer them without another
search).

**Decisions.**

- **D2. Wikidata as the hub.** Recommendation: yes. The alternative, a
  search on each site with its own fuzzy matching, multiplies the error
  rate by the number of sites and still cannot cross-check one site
  against another. The risk is coverage for small works (web serials, small
  albums, podcasts); step 3 and "not found" cover those, and the backfill
  report will say how many.
- **D3. Model as tiebreaker only**, not as the matcher. Recommendation:
  yes. Deterministic matching is predictable and free; the model handles
  the cases a rule cannot ("Dune" the 1984 film or the 2021 one when the
  log has neither year nor director). Expected volume is tens of calls,
  well under a cent each.
- **D4. Logged date is a weak signal.** It is when you finished the work,
  not when it came out. Recommendation: use it only to exclude candidates
  released after it, never to prefer close years.

**Tradeoffs.** Wikidata search is a general search engine, not a title
index; "Pantheon" returns the Paris mausoleum first. The claims-based
scoring is what makes it work, which means fetching ten items per search
(one batched `wbgetentities` call, so one request). The ambiguity cases
will be real (remakes, same-name books and films, the Harry Potter books
and films logged separately); the type filter does most of that work.

**Acceptance.** On a sample of 50 entries chosen across types, at least
90 % come back confident or check with the right answer, and every wrong
confident match is explained. The sample result is checkpoint 1 (section
4) before anything else is built on it.

---

## T3. Fetchers: details, links and scores

**Scope.** From a resolved identity, collect what the metadata line, the
links line and the scores need. One small module per site, each a function
`fetch(ids) -> partial` that returns details, links, scores, poster
candidates and source genres.

**Per type.**

| Type | Details from | Scores | Links (from Wikidata ids) |
|---|---|---|---|
| TV | TMDB (first/last air date, seasons, episodes, networks); MAL for anime | IMDb, Rotten Tomatoes, Metacritic, MAL | Wikipedia, IMDb, TVDB, TMDB, MAL, AniDB, ANN, RT, Metacritic, official site |
| Movie | TMDB (release, runtime, studio); MAL for anime films | IMDb, Rotten Tomatoes, Metacritic, MAL | Wikipedia, IMDb, TMDB, Letterboxd, RT, Metacritic, MAL |
| Book | Open Library (first published, cover), Wikipedia | none (see D8) | Wikipedia, Goodreads, Open Library, official site |
| Game | Steam app details (release, developer, publisher, genres, Metacritic) | Metacritic, Steam review summary if clean | Wikipedia, Steam, Metacritic, official site |
| Album | MusicBrainz release group (year, tracks), Cover Art Archive | none | Wikipedia, MusicBrainz, Spotify (Notion), Bandcamp if in Wikidata |
| Podcast | iTunes search (artwork, genre, first episode) | none | Apple Podcasts, official site |

Wikipedia's summary endpoint gives the article URL, a one-paragraph extract
and a lead image for every type. Wikidata itself gives seasons, episodes,
network and dates as a fallback when TMDB has nothing.

**Scores.**

- **IMDb**: the public `title.ratings.tsv.gz` dataset (8.7 MB, fetched
  fine), downloaded to the worker cache and refreshed when older than 30
  days. No page fetches. The IMDb datasets are licensed for personal and
  non-commercial use, which this is.
- **Rotten Tomatoes and Metacritic**: their own pages, at the exact path
  Wikidata gives (`tv/pantheon` for both), reading the score from the
  page's embedded JSON. Pantheon's pages returned 100 % and 77, matching
  the mock. robots.txt allows these paths. One request per page, at most
  one every two seconds per host, cached.
- **MAL**: the official MAL API (needs a free client id). Metallic Rouge's
  page shows 6.21, matching the mock.
- **Steam**: the store API's `metacritic` field for games.

**Implementation.** `worker/src/tropes_worker/lookup/` with `wikidata.py`,
`wikipedia.py`, `tmdb.py`, `mal.py`, `steam.py`, `openlibrary.py`,
`musicbrainz.py`, `itunes.py`, `imdb.py`, `scores.py` (RT and Metacritic),
and `merge.py`, which combines partials with a fixed precedence (TMDB over
Wikidata for TV dates, MAL over TMDB for anime episode counts, and so on).
`httpx` with one async client, a per-host rate limiter and a
`User-Agent: TropeLog/0.1 (+repo URL)` header as Wikidata and MusicBrainz
ask. Raw responses are cached on the worker under
`data/cache/lookup/<host>/<sha1(url)>.json`, so `merge.py` can be changed
and re-run over the whole library without fetching anything again.

**Decisions.**

- **D5. TMDB with an API key.** Recommendation: yes. It is the best source
  for TV dates, season and episode counts, networks and 2:3 posters, and the
  key is free. Without it, Wikidata alone gets Pantheon wrong: its end date
  is season 1's (October 2022), where the mock says 2022 to 2023.
  **Needs from you:** a TMDB account and its API read access token as
  `TROPES_TMDB_TOKEN`.
- **D6. MAL through the official API.** Jikan, the usual keyless proxy,
  timed out from ivory on all three tries today; MAL's own pages load but
  scraping them is brittle. Recommendation: the official API with a client
  id (free, registration only). **Needs from you:** `TROPES_MAL_CLIENT_ID`.
- **D7. Rotten Tomatoes and Metacritic from their pages.** The
  alternatives: OMDb (free key, 1000 requests a day; as far as I know it
  carries RT and Metacritic for films but rarely for TV, so Pantheon would
  likely get neither; not tested without a key), or no scores for these
  two. Recommendation: read the pages, politely, only
  at paths Wikidata supplies, never searching their sites. It is a gray
  area under their terms; at a few hundred requests a month for a personal
  site I think it is fine, but it is your call.
- **D8. Books and albums get no scores.** Goodreads has had no API since
  2020 and its pages are scrape-hostile; Open Library ratings are sparse.
  Recommendation: links only. Your own rating is the score that matters on
  this site.
- **D9. TVDB, Letterboxd, Goodreads, AniDB, ANN: links only**, built from
  the ids in Wikidata. TVDB's API now needs a paid licence and TMDB covers
  the same data. Recommendation: yes.
- **D10. No IGDB, no Spotify API, no Google Books.** Each needs another key
  for data the table above already gets. Revisit if the backfill report
  shows a type badly covered (non-Steam games are the likely one; IGDB is
  the fix, free with a Twitch developer account).

**Tradeoffs.** Ten small modules is more files than one big one, but each
is 30 to 80 lines with one site's quirks in it, which is what you want to
read when a site changes its format. The raw cache costs a few tens of MB
for the whole library; it buys free re-merges and a record of what each
site said.

**Acceptance.** Pantheon's merged result matches the mock: 2022 to 2023,
2 seasons, 16 episodes, IMDb tt11680642, Metacritic 77, Rotten Tomatoes
100 %. Metallic Rouge's matches its mock: Bones, original, January 11 to
April 4, 2024, 13 episodes, Action and Sci-Fi, MAL 6.21. Unit tests run
every fetcher's parser against a saved response.

---

## T4. Posters

**Scope.** A local poster for every entry that has one anywhere, the ~600
without a Notion Image Link included.

**Approach.** Precedence: Notion Image Link (yours, always wins) → TMDB
poster → Steam's 600×900 library capsule → MAL → Open Library cover →
Cover Art Archive → iTunes artwork → Wikipedia lead image. The worker
downloads the first that exists, resizes with Pillow to 300 px wide
(the column is 150 px, so 2×), encodes WebP, and uploads it with
`PUT /api/media/:id/poster` (bearer token, size and type checked). The site
writes `data/posters/<id>.webp`, sets `poster_path` and `poster_source`,
and serves it from `/posters/<id>.webp` with a long cache header and the
file's mtime as a version query. When a re-import changes the Image Link,
`poster_source` no longer matches and the next refresh fetches it again.

**Decisions.**

- **D11. Worker fetches and resizes, site stores.** Recommendation: yes. It
  keeps the site free of outbound requests, and the upload endpoint is the
  same one Phase 5 needs for frames.
- **D12. One size, 300 px WebP.** Roughly 20 KB each, ~15 MB for the
  library. Recommendation: yes; the poster appears in one place at one size.
  Square art (albums, podcasts) is kept square.

**Acceptance.** No page on the site references an outside image host;
Pantheon shows the theposterdb poster from Notion, served locally.

---

## T5. Genres and the library filter

**Scope.** Genres on the metadata line and a genre filter in the library.

**Approach.** A fixed vocabulary in `web/seed/genres.json`, about 30
entries, written for this library rather than copied from any one source
(Science fiction, Fantasy, Horror, Mystery, Thriller, Romance, Comedy,
Drama, Action, Adventure, Historical, Literary, Superhero, Animation,
Anime, Documentary, Nonfiction, Strategy, Roguelike, Puzzle, Platformer,
Shooter, Simulation, RPG, Rock, Electronic, Hip hop, Pop, Folk, Jazz,
Classical, and so on; you edit the list). For each entry one model call
gets the source genres every fetcher returned (TMDB genres, MAL genres and
themes, Steam genres, Open Library subjects, MusicBrainz tags, Wikidata
genre labels) and picks one to three from the vocabulary. The library gains
a Genre row in the filter block, plain text options as Type is now.

**Decisions.**

- **D13. A controlled vocabulary, assigned by the model.** The sources'
  own genres disagree in kind and number (Open Library returns dozens of
  subject strings per book, TMDB has "Sci-Fi & Fantasy" as one genre), so
  showing them raw would give a filter with hundreds of values.
  Alternatives: a hand-written mapping table (deterministic, but books and
  albums have open-ended tags it could never cover), or the model writing a
  free phrase per work. Recommendation: vocabulary plus model; about 800
  short calls, under 20 cents for the library. Owner edits stick.
- **D14. The Pantheon mock's genre phrase was hand-written.** "Cyberpunk,
  conspiracy thriller" is not what any source says. Recommendation: the
  acceptance test for Pantheon checks genres from the vocabulary (likely
  "Science fiction, Thriller, Animation") rather than the mock's phrase. If
  you want the phrase style, the alternative is a second, free-text
  `genre_line` the model writes and you can edit; it costs nothing extra
  but it is one more field of model prose on public pages.

**Acceptance.** The library filters by genre; every genre in the
vocabulary that is used at least once appears as an option.

---

## T6. Media page

**Scope.** Render what T1 to T5 stored, and give the owner the three
corrections a lookup needs.

**Approach.**

- Metadata line, one template per type, built in `web/src/lib/media.ts`
  where the stub already lives:
  - TV: "TV series, 2022 to 2023, 2 seasons, 16 episodes. Science
    fiction, Thriller. Watched November 2022."
  - Movie: "Movie, 1999, 2 h 16 min. …"; Book: "Book, 2019. …"; Game:
    "Game, 2016, Respawn Entertainment. …"; Album: "Album, 1997, 12
    tracks. …"; Podcast: "Podcast, 2014 to 2022. …". Studio or network goes
    in for TV and film only when it adds something (anime studio, yes).
- Links line in the margin, fixed site order per type, scores after the
  site name ("Metacritic 77"), hidden links omitted.
- Owner only, under the links line: "Edit links" (hide a link, add one by
  URL; the site is recognised from the host), "Edit genres" (checkboxes
  from the vocabulary), and "Wrong match", which lists the stored
  runners-up and a "No match" option, and queues a refresh after a change.
  All three are server-rendered forms through Actions, the Phase 2 pattern.

**Decisions.**

- **D15. No automatic descriptions.** The Wikipedia extract is shown in
  add-media step 2 and on the review page to confirm identity, and it feeds
  dossiers (D16), but it never becomes the public description.
  Recommendation: yes. The description is your voice; an encyclopaedia
  paragraph would read wrong next to it.

**Acceptance.** Pantheon's header matches the mock apart from D14; the
three owner forms work without JavaScript.

---

## T7. Backfill and its review page

**Scope.** Run the lookup over the whole library once, and let you confirm
it in one sitting rather than 776.

**Approach.** `lookup_media` takes a list of media ids (one for add media
or a refresh, all of them for the backfill) and returns one proposal per
entry (proposal kind `match`, the existing proposal table, payload in its
JSON). `/metadata` (owner) shows the job in three sections:

1. **Check these** first: ambiguous and per-site-only matches, each with the
   chosen candidate and its runners-up as radio options (title, year,
   creator, Wikipedia first sentence, poster thumbnail), plus "No match".
2. **Not found**: a list, nothing to do unless you know better ("Add a
   link" lets you paste an IMDb, Steam or Wikipedia URL, which becomes the
   seed for a re-run).
3. **Confident**: collapsed to a count with "Show all", each pre-checked.

One "Commit" writes identities, details, links, scores, genres and posters
for everything checked. Unchecked entries stay unresolved and come back in
the next backfill. Posters are fetched during the job and uploaded to a
staging name; commit moves them into place, so nothing appears on a public
page before commit.

**Decisions.**

- **D16. Feed Wikipedia into dossiers.** The 67 subjects whose dossiers
  say the model knows them partly or not at all get the Wikipedia extract
  (and plot section where one exists) as an extra input, and are rebuilt.
  Recommendation: yes, it is the cheapest recall improvement available
  before Phase 5 (cents) and uses data this phase fetches anyway. It means
  a `dossier` prompt version bump, which by the Phase 3 rule rebuilds only
  what changed inputs.
- **D17. Rate and time.** Six to ten requests per entry spread across
  hosts, per-host limits (Wikidata and TMDB a few per second, MusicBrainz
  one per second, RT and Metacritic one per two seconds). My estimate for
  the whole library is under an hour; the sample in checkpoint 1 will
  measure it.

**Acceptance.** After one backfill and one review sitting, every entry is
confirmed, marked no-match, or listed as not found; the report counts each
by type.

---

## T8. Add media, step 2

**Scope.** Spec 6.6 in full: type a title, look it up, confirm what was
found, check against all tropes, add to library.

**Approach.** Step 1 posts a title (year and type optional) and queues
`lookup_media` in query mode, which runs T2 to T5 for a work that has no
media row yet. Step 2 shows: canonical title; details; the Notion entry if
the title matches one in the library (then this is a lookup for an
existing row, and the page says so); the local copy if one is linked;
links with checkboxes and scores; "Add a link"; the poster with "Use a
different image" (paste a URL). "Looks right" queues the Phase 3
`check_subject` job against the confirmed identity, and the trope
proposals appear below on the same page with the calibration line
("Checked against all 27. Two matched; nothing else scored above 0.3.").
"Add to library" commits the media row, its metadata and the checked
instances in one transaction. "Wrong match" shows the runners-up; "Start
over" discards both jobs.

**Decisions.**

- **D18. A site-created entry is not written to Notion.** Sync stays one
  way (decided 2026-10-19). The importer already matches on title and type
  when a Notion id is missing, so when you later log the work in Notion the
  next import adopts the site row instead of duplicating it.
  Recommendation: keep that, and show "Not in your Notion log yet" on the
  media page for owner eyes only.

**Acceptance.** A work not in the library (say, a film you have not logged)
goes through all three steps and its page shows metadata, links, poster
and the committed tropes; Start over leaves nothing behind.

---

## T9. Notion sync through the API (optional)

**Scope.** Replace "export a CSV, run `just import`" with
`just sync-notion`, which reads the Media Log through Notion's API and
feeds the existing importer.

**Approach.** An internal integration token with read access to the Media
Log, one paginated query of the data source, rows mapped to the same
shape the CSV parser produces, then the existing upsert. Media Link or
Image Link changes queue a refresh for the affected entries. A timer comes
with Phase 6.

**Decisions.**

- **D19. Build it now or keep CSV.** The dev database still comes from the
  canvas export plus the Notion connector backfill, not from a real export
  of your log, and the lookup reads the Image and Media Links, so the
  library should be synced before the backfill either way.
  Recommendation: build it (a small script on top of the importer), because
  you said Notion changes should propagate and a hand export each time is
  the step that will not happen. **Needs from you:** a Notion internal
  integration shared with the Media Log, token as `NOTION_TOKEN`. If you
  would rather not, one fresh CSV export before the backfill does the same
  job once.

---

## T10. Operations, tests, docs

- Keys in the repo-root `.env`: `TROPES_TMDB_TOKEN`,
  `TROPES_MAL_CLIENT_ID`, and `NOTION_TOKEN` if T9 is approved.
- `just lookup <title|id>` queues a single lookup; `just backfill-metadata`
  queues the whole library; `just refresh-metadata` re-fetches scores and
  details for pinned identities (manual for now, the timer is Phase 6).
- The worker skips any fetcher whose key is missing and says so in the job
  warnings, so a missing key degrades coverage rather than failing the job.
- Tests: every fetcher's parser against a saved response; `merge.py`
  precedence; the identity scorer against a table of hand-checked cases
  (Pantheon the series not the mausoleum, Dune the right film, the Harry
  Potter book and film rows resolving to different items); site side, the
  poster upload checks and the ownership rules on re-import and refresh.
- Docs: `worker/README.md` gains a section on `lookup_media` and the
  per-site modules; `ROADMAP.md` Phase 4 status updated at the end.

---

## 2. Decisions needing your answer

Everything above has a recommendation; these change what gets built or
need something from you.

1. **D5, D6: keys.** A TMDB API read access token and a MAL client id,
   both free. Without TMDB, TV and film details fall back to Wikidata
   (Pantheon's end year would be wrong) and posters to Wikipedia images.
2. **D7: Rotten Tomatoes and Metacritic** scores read from their pages
   (recommended), from OMDb (mostly films, another key), or not shown.
3. **D13, D14: genres.** A controlled vocabulary assigned by the model
   (recommended), and whether you also want a free genre phrase like the
   mock's "Cyberpunk, conspiracy thriller". If the vocabulary, glance at
   the list in T5 and tell me what to add or cut.
4. **D19: Notion sync** through the API (recommended, needs an integration
   token) or one fresh CSV export before the backfill.
5. **D16: Wikipedia into dossiers** for the 67 weakly known subjects:
   yes (recommended) or leave dossiers for Phase 5.

---

## 3. What was probed from ivory on 2026-10-21

| Source | Result |
|---|---|
| Wikidata search and entity data | Works. Pantheon by IMDb id → Q109639866 with IMDb, TMDB, TVDB, RT and Metacritic slugs, official site, genres, 2 seasons, 16 episodes, network, dates (season 1's end date only). Plain title search for "Pantheon" ranks the Paris building first. |
| Wikipedia REST summary | Works; carries the Wikidata id and a lead image. |
| TMDB, OMDb | Reachable; both need a key (401 without). |
| MyAnimeList | Jikan timed out three times (30 s). The MAL page loads and shows 6.21 for Metallic Rouge; the official API answers 403 without a client id. |
| Steam store API | Works keyless (Titanfall 2 app details). |
| Open Library | Works keyless (Gideon the Ninth with cover id and subjects). |
| MusicBrainz | Busy (503) on the first try, fine on the second; it asks for one request a second. |
| iTunes search | Works keyless (Hello Internet). |
| IMDb datasets | `title.ratings.tsv.gz` downloads, 8.7 MB. |
| Rotten Tomatoes, Metacritic | Pages load; embedded JSON gives Pantheon 100 % and 77. robots.txt does not disallow these paths. |
| Spotify oEmbed | Works keyless (album art), but the link Notion shares across nine albums resolves to one album, so it is unusable for those. |

Library coverage today: 170 of 776 entries have a Notion Image Link
(75 theposterdb, 34 Spotify art, 29 Wikimedia, 21 Amazon, others); 208 have
a Media Link, 194 of them with an id usable as a seed. Metallic Rouge is already in the library
(no Image or Media Link), so T8's acceptance needs a work that is not.

---

## 4. Order of work and checkpoints

1. T1, T2 and the Wikidata and Wikipedia fetchers, run over a 50-entry
   sample with no writes. **Checkpoint:** the resolution report (confident,
   check, not found, by type, with the wrong ones explained) and the
   measured time per entry, before building on it.
2. T3, T4, T5 over the same sample. **Checkpoint:** Pantheon and Metallic
   Rouge merged results against the mock, ten posters, the genre
   assignments.
3. T9 if approved, then sync, then T7 and the full backfill. **Checkpoint:**
   you review `/metadata` and commit.
4. T6 and T8. **Checkpoint:** you add a new work end to end.
5. T10 and D16's dossier rebuild.
