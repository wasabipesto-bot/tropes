# tropes-worker

The pipeline half of Trope Log. It runs wherever the local media lives (ivory
for now), claims jobs from the site over HTTP, does the slow work (model
calls, text extraction, quote checking) and posts results back. It never
opens the site's database.

```
uv sync
uv run tropes-worker ping                 # is the site up?
uv run tropes-worker run                  # claim and run jobs until stopped
uv run tropes-worker run --once           # one job, then exit (debugging)
uv run tropes-worker eval --trope dog-duo # score the scan against verified instances
uv run tropes-worker sync                 # read the Notion Media Log once and hand the rows to the site
uv run tropes-worker lookup --sample 50   # resolve identities for a sample; prints a report, writes nothing
```

From the repo root: `just worker`, `just eval --trope dog-duo`, `just api-key
<name>` to mint the bearer token. `ops/tropes-worker.service` is a systemd
user unit for ivory.

## Configuration

Environment variables, also read from a `.env` in the worker directory or the
repo root. Values in parentheses are defaults.

| Variable | Purpose |
|---|---|
| `TROPES_SITE_URL` (`http://127.0.0.1:4321`) | the site |
| `TROPES_API_TOKEN` | bearer token from `just api-key` |
| `OPENROUTER_API_KEY` | required for every job except `ping` |
| `TROPES_MODEL` (`deepseek/deepseek-v4.1-flash-1017`) | model for everything |
| `TROPES_MODEL_DOSSIER` (same as `TROPES_MODEL`) | model for dossier builds, e.g. a `:batch` variant |
| `TROPES_REASONING` (`default`) | `off`, `low`, `medium`, `high`, or `default` to send nothing. Off is about eight times faster and scored worse in a quick probe |
| `TROPES_LLM_CONCURRENCY` (8) | concurrent model calls inside a job |
| `TROPES_TEMPERATURE` (0.3) | one temperature for every prompt |
| `TROPES_PASS1_BATCH` (25) | dossiers per pass-1 call |
| `TROPES_PASS2_MIN_SCORE` (0.3) | pass-1 score needed to reach pass 2 |
| `TROPES_PASS2_CAP` (60) | most candidates read in pass 2, seeds excepted |
| `TROPES_UNCHECKED_BELOW` (0.5) | review-page checkbox starts unchecked under this |
| `TROPES_JSON_SCHEMA` (0) | send `response_format: json_schema`. Off: with DeepSeek the constrained decoding degenerated into 100k-token truncated replies; prompt-only JSON validated locally is fast and complete |
| `TROPES_RESPONSE_HEALING` (1) | with the schema path, also ask OpenRouter to repair malformed JSON |
| `TROPES_SOURCES_DIR` (`<repo>/data/sources`) | where relative text-source paths resolve |
| `TROPES_TEXT_CACHE_DIR` (`<repo>/data/text`) | extracted text, keyed by file hash |
| `TROPES_MIDDEN_KEY` | key for the Tumblr archive search; without it dossiers skip the owner's posts |
| `NOTION_API_KEY` | read-only integration shared with the Media Log; the loop queues a `sync_notion` job every `TROPES_NOTION_SYNC_MINUTES` (15; 0 disables) |
| `TROPES_TMDB_TOKEN` | TMDB API read access token; without it TV and film details fall back to Wikidata |
| `TROPES_MAL_CLIENT_ID` | MyAnimeList API client id; without it anime details and scores are skipped |
| `TROPES_LOOKUP_CACHE_DIR` (`<repo>/data/cache/lookup`) | raw responses from every metadata source, keyed by URL, so merges can be re-run without fetching |

## Job kinds

- `ping`: round trip, no model.
- `build_dossiers`: for every media item that needs one (missing, older
  prompt version, or a text source appeared or changed), fetch the owner's
  Tumblr posts about it, keep the relevant ones, and write the dossier; then
  one dossier per series from its members'. Posted in batches of 20 so a
  crash keeps what was done. Payload `{onlyMissing, subjects?}`.
- `scan_trope`: pass 1 scores every subject from its dossier in batches; pass
  2 reads the candidates (full text when a source is linked) and writes the
  entry; quotes are checked verbatim against the text and dropped if absent.
  Payload `{mode: add|recheck, tropeId?, draft?}`. Rechecks also look for new
  evidence on existing instances that have a text source.
- `check_subject`: one work or series against every trope in one call, plus
  new evidence for its existing instances on a recheck. Payload `{mode, subject}`.

- `sync_notion`: read every row of the Media Log through Notion's API and
  post them to `POST /api/import/notion`; the site upserts, marks rows that
  stopped coming back, and queues `lookup_media` for new entries.
- `lookup_media`: for each work, resolve its identity (an exact id from the
  Notion Media Link, else a Wikidata search restricted to the type's classes
  and scored on title, class, creator and year; the model only breaks ties;
  per-site search when Wikidata has nothing), then fetch details, links and
  scores from TMDB, MAL, Steam, Open Library, MusicBrainz, iTunes, the IMDb
  ratings dataset and the Rotten Tomatoes, Metacritic and Goodreads pages,
  download the first usable poster into 900/300/50 px WebP uploads, and map
  the sources' genres onto the site's vocabulary. Payload
  `{mediaIds, auto?, refresh?, poster?}`; `refresh` re-fetches from the pinned
  identity and never re-matches. The result is one `match` proposal per work;
  with `auto`, confident matches are committed by the site at once.
- `write_blurbs`: a two- or three-sentence description draft per work from
  its dossier and Wikipedia extract; non-answers are dropped. Payload `{mediaIds}`.

Phase 5 adds the file jobs, which only the media worker takes (the one with
`TROPES_MEDIA_ROOT` set; it takes nothing else), and three model-side jobs
that read what it produced:

- `index_local` (media): walk the media root (Plex-style `Movies/`, `TV/`,
  `Anime/` folders and a Calibre `Books/` library), match folders and books to
  the library by title, year and ids, probe each file's streams with ffprobe,
  and post one row per episode, film or book to `POST /api/sources`. Payload
  `{mediaIds?, auto}`. The summary counts matches by outcome; the warnings
  list works not on the disk and folders to check (shown on `/review`).
- `extract_text` (media): the subtitle text of each video source (an English
  sidecar file, else an embedded track, else OpenSubtitles while the day's
  quota lasts) and the text of each book (EPUB, MOBI, TXT), rendered with
  `## S01E01 Title` headings and `[12:40]` stamps, posted to
  `POST /api/sources/:id/text`. Payload `{sourceIds?, auto}`.
- `extract_evidence` (media): a frame (WebP) or clip (mp4) at each timestamped
  quote, uploaded to `POST /api/evidence/file`. Queued by the site after a
  scan (`{items, forJob}`) and by the Clip button.
- `make_sheets` (media): contact sheets per video source, keyframes every
  45 s tiled 10×6 at 288 px, one JPEG per 45 minutes, uploaded to
  `PUT /api/sources/:id/sheet/:n`. Payload `{sourceIds?, auto}`.
- `read_sheets`: the model looks at each sheet and writes down what is shown
  but never said (looks, props, settings, on-screen text), stored as
  `media_note` rows with source `visual` and the episode label; the dossier
  prompt reads them as a "Visual notes" block. Payload `{sourceIds?, auto}`.
- `look_frames`: for a scan's proposals of tropes marked "Visual trope, use
  screenshots", the model looks at the frames grabbed at the quoted moments
  and says whether the trope is in the picture; the site flags the proposal
  and halves its score when it is not. Payload `{forJob, auto}`; queued by the
  site when the frames land.
- `fetch_wiki`: Fandom article text for pinned works with a Wikidata Fandom
  id (P6262), stored as a `wiki` note the dossier reads, plus `/Transcript`
  pages linked as text sources where a wiki keeps them. No model calls.
  Payload `{mediaIds?, auto}`.

On the model side, `ensure_texts` pulls the extracted texts into
`data/text/site/` before a scan or dossier build, one file per work in
episode order, so the rest of the pipeline reads them like a linked EPUB.
Texts over `TROPES_TEXT_CAP_TOKENS` (default 600k) are read in blocks that
break between seasons: the dossier is built per block and merged through the
series-dossier prompt, and pass 2 reads the block the pass-1 reason names (an
episode label or title) plus the next one.

Results carry `usage` (calls, tokens, cost in USD as OpenRouter reports it)
and `warnings`; the review pages show both.

## Metadata sources

`src/tropes_worker/lookup/`: one module per site (`tmdb`, `mal`, `steam`,
`openlibrary`, `musicbrainz`, `itunes`, `imdb`, `scores`), each a `fetch(ids)`
returning a `Partial` and a `search(title)` returning candidates; `wikidata`
and `wikipedia` for the identity hub and extracts; `resolve` for the scoring;
`merge` for the per-type precedence; `posters` and `genres`; `http` for the
one polite client (per-host gaps, project User-Agent, raw-response cache).
Every parser has a test against a saved response in `tests/fixtures/lookup/`.

## Prompts

`src/tropes_worker/prompts/*.md`. Each file may start with `version: N`
frontmatter; dossiers are rebuilt only when that number rises, so wording can
be tuned without a rebuild. `system.md` carries the writing rules from the
spec and is sent with every call. Every reply is validated against the
pydantic models in `schemas.py`; one retry carries the validation error back
to the model.

## OpenRouter notes

- Structured output: prompt-only JSON, validated with pydantic, one retry
  with the complaint. `TROPES_JSON_SCHEMA=1` switches to `response_format:
  json_schema` plus the Response Healing plugin; measured on DeepSeek V4.1
  Flash that path took 20 to 500 seconds per dossier and produced truncated
  lists, against 9 seconds and full lists without it.
- Batch API: OpenRouter has one (`POST /api/v1/batches`, 24-hour window,
  about half price, only models with a `:batch` endpoint). The worker does not
  use it yet; `TROPES_MODEL_DOSSIER` can point at a `:batch` variant for the
  one-off dossier build if the slower route is acceptable, and a true batch
  path is a small addition if it ever matters.
- More than one worker: `claim` is atomic, so a second worker is safe to run.
  Whether it helps depends on OpenRouter throughput, not on the site.
