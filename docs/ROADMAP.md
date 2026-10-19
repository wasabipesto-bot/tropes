# Trope Log: implementation roadmap

Written 2026-10-19 against `SPEC.md` (the Claude Design handoff). This document
proposes a stack, an architecture, an auth design and a phased build order. It
also lists what the spec left open and what I recommend for each. Nothing here
is built; every phase is a proposal until it is approved.

Sizes are relative (S/M/L/XL) and mean effort, not calendar time.

---

## 1. Summary of the proposal

- **Site**: Astro 7 in server mode behind the Node adapter, one SQLite file,
  Drizzle for schema and migrations, plain TypeScript islands for the few
  interactive pieces. No React. Source Serif 4 self-hosted.
- **Pipeline**: a separate worker process, in Python, that runs next to the
  local media library. It talks to the site over an authenticated HTTP job API.
  It never touches the SQLite file directly.
- **Auth**: single owner. Password login with a server-side session cookie;
  passkey added later as a convenience. A separate bearer token for the worker.
  Public visitors get the same pages with the controls removed.
- **Hosting**: one container for the site (plus its SQLite file and evidence
  files on a volume) on whichever box survives the homelab migration, or a small
  VPS. Cloudflare in front. The worker runs wherever the media is.
- **Order**: library and media pages first (read-only, importable from Notion),
  then tropes with manual authoring and auth, then the matching pipeline on
  cheap inputs, then external metadata and posters, then local media indexing
  and evidence extraction, then public hardening.

The main design addition over the spec is a per-work **dossier**: a structured
summary the pipeline builds once per media item and reuses for every trope
scan. Section 4 explains why.

---

## 2. Stack

### 2.1 Recommended: Astro + SQLite, Python worker

| Layer | Choice | Notes |
|---|---|---|
| Framework | Astro 7.4 (current as of writing), `output: 'server'`, `@astrojs/node` | Astro 7 is newer than my training data. First task in Phase 1 is to read the current docs for Actions, middleware, sessions and `checkOrigin` before scaffolding. |
| Database | SQLite via `better-sqlite3` + `drizzle-orm` / `drizzle-kit` | 778 works, dozens of tropes, low thousands of instances. One file, WAL mode, FTS5 for search. Backups are a file copy; Litestream to R2 if wanted. Node 24 ships `node:sqlite` but it still warns as experimental, so stay on better-sqlite3. |
| Markup | Astro components, scoped CSS, no UI library | The spec's visual system is small and specific. A component library would fight it. |
| Interactivity | Astro Actions for mutations, small vanilla `<script>` islands | Needed for: spoiler toggles, verification toggle, inline edit panels, autocomplete, the add/recheck review lists, "show all" on the library. If the review lists get unwieldy, add Svelte for those two pages only. |
| Text format | A tiny custom parser for `[[Trope name]]` and `||spoiler||`, plus a restricted Markdown subset (paragraphs, italics, links) | Render server-side to HTML. Spoilers must render as the same inline element in both states (spec 4). |
| Fonts | Source Serif 4 variable, self-hosted woff2 | No Google Fonts request on a public page. |
| Worker | Python 3.12+, `uv`, Anthropic SDK, `ffmpeg` CLI, `ebooklib`, `pysubs2`, `faster-whisper` (only if subtitles are missing) | See 2.3 for why Python. |
| Packaging | Docker Compose: `web` (site + volume), `worker` (optional, usually runs elsewhere) | `justfile` for dev, build, migrate, import, deploy. |
| CI | GitHub Actions: typecheck, lint, unit tests, build, Python tests | Same shape as the other repos. |

### 2.2 Alternatives considered

**Postgres instead of SQLite.** Nothing in the spec needs it. SQLite removes a
service, makes dev and prod identical, and makes backup a file copy. Revisit
only if the site ever needs more than one writer process. (Keep the worker off
the database file; see 3.2.) Drizzle keeps the schema portable if it ever
changes.

**Cloudflare Workers + D1 + R2 instead of a Node container.** Serious option.
Hosting would be free and there is no server to patch. The worker has to talk
over HTTP anyway, so the architecture does not change. Costs: D1 is SQLite but
local dev goes through wrangler, evidence files go to R2 instead of disk, and
Astro-on-Workers has sharper edges than Astro-on-Node. Recommendation: Node
container first. The switch is contained to the DB driver and a blob-storage
interface, so it stays open if hosting becomes the problem.

**SvelteKit instead of Astro.** Better fit for the owner flows (review lists,
inline edits), worse fit for nothing in particular. Astro Actions plus a few
islands cover the owner flows, and you know Astro. Not recommended.

**Rust (axum + maud) for the site.** Type-safe, single binary, small. But the
site is mostly templating with many small interactive affordances, which is
slow to iterate in Rust. Not recommended for the site. For the worker, see 2.3.

### 2.3 Worker language: Python, not TypeScript

Arguments for TypeScript: one language, shared types between site and worker.
Arguments for Python: every library the expensive pass needs (EPUB parsing,
subtitle parsing, Whisper, image handling, PDF) is better in Python, and the
job API contract is small enough to define once as JSON Schema and generate
both sides, or just hand-write a pydantic model and a zod schema that are
checked against each other in CI with a fixture file.

Recommendation: Python worker. If the schema duplication turns out to be
annoying, that is a Phase 3 problem and cheap to fix then.

### 2.4 LLM provider and models

Direct Anthropic API through the official SDK. Model split, as a proposal:

| Step | Model | Why |
|---|---|---|
| Dossier build (once per work) | `claude-sonnet-5` | Bulk reading. Batch API halves the price. |
| Pass 1 candidate scoring | `claude-sonnet-5`, or `claude-haiku-4-5` if it calibrates well on the seeds | Many short calls, needs recall more than nuance. |
| Pass 2 judgment, `who`, text, prominence, evidence locators | `claude-opus-5` | This is the text the public reads. Quality matters here; the volume is small. |

Use prompt caching: the trope description and writing rules are the stable
prefix in pass 1; the work's full text is the stable prefix when checking one
work against all tropes. Cost estimates in section 7.

Open to using OpenRouter instead, as tumblr-search does, if you prefer one
bill. The worker isolates the call behind one function either way.

---

## 3. Architecture

### 3.1 Components

```
 browser ──► Astro site (Node) ──► SQLite (one file, WAL)
                 │                   └── data/evidence/  (frames, clips, posters)
                 │
                 │  HTTPS, bearer token, long-poll
                 ▼
          worker (Python, in the homelab next to Plex)
                 ├── Anthropic API
                 ├── local media: EPUB, MKV/MP4, subtitles
                 └── external metadata: TMDB, Jikan (MAL), Wikipedia, TVDB, Open Library, Steam
```

The site is the only process that writes the database. The worker is a client:
it claims jobs, does the slow work, and posts results back. This keeps SQLite
single-writer, lets the worker live where the media is, and needs no inbound
port into the homelab.

### 3.2 Job API

Tables: `jobs` (id, kind, payload JSON, status, progress JSON, result JSON,
created, claimed_at, finished_at, error). Kinds in v1: `scan_trope`,
`check_media`, `recheck_trope`, `recheck_media`, `build_dossier`,
`lookup_media`, `index_local`, `extract_evidence`.

Endpoints (owner token or worker token):

- `POST /api/jobs` create (site-internal, called by Actions)
- `GET /api/jobs/claim?kinds=…` worker long-polls, gets one job, status → running
- `PATCH /api/jobs/:id` progress updates (`{done: 312, total: 778}`)
- `POST /api/jobs/:id/result` final result; status → done
- `POST /api/evidence` multipart upload of a frame or clip, returns a file id
- `GET /api/export/works`, `GET /api/export/tropes` read models for the worker

The add/recheck pages create a job and poll `GET /api/jobs/:id` every second or
so. Results are a proposal set the page renders for review. Nothing in the
proposal touches `instances` until the owner commits.

If the site and worker end up on the same host, this still works and costs
nothing. Do not add a "direct DB" mode.

### 3.3 Repository layout

```
tropes/
  web/            Astro site, schema, migrations, Actions, API routes
  worker/         Python pipeline (uv project)
  docs/           SPEC.md, ROADMAP.md, later DECISIONS.md
  compose.yml
  justfile
```

---

## 4. The matching pipeline

### 4.1 Why a dossier

The spec's two passes read "title, synopsis, metadata, notes" in pass 1 and
full text in pass 2. Two problems:

1. Title plus synopsis is a weak signal for most tropes. Dog Duo in
   *The Ancient Magus' Bride* is not in any synopsis.
2. Every new trope re-reads the full text of its candidates. Thirty candidates
   at 100k tokens is 3M tokens per trope; across dozens of tropes that is the
   whole corpus read many times.

A dossier is a structured summary built once per work and reused by every
scan: characters with roles and descriptors, relationships, settings,
arcs with locators, recurring imagery and motifs, themes, notable scenes with
locators. Depth levels:

- `metadata`: built from external metadata, synopsis, and your own writing. Cheap, available for everything in Phase 3.
- `full`: built from indexed local text (EPUB, subtitles). Phase 5. Replaces the metadata dossier when available.

Pass 1 then reads dossiers, not synopses, and gets much better recall. Pass 2
still reads the source text, but only for candidates, and only to confirm,
write the entry, and find evidence.

Dossiers are internal. They are never shown on the site.

### 4.2 Passes

1. **Pass 1** (per trope): batch ~25 dossiers per call, ask for a 0–1 score per
   work and a one-line reason. ~32 calls for 778 works, run concurrently.
   Seeds are always carried to pass 2 regardless of score, so calibration can
   be reported honestly.
2. **Pass 2** (per candidate above a threshold, plus seeds): the trope
   description, writing rules, the dossier, and the indexed text if any. Output:
   final score, prominence, `who`, text, up to N evidence locators. Opus 5.
3. **Evidence extraction** (per accepted locator): quote text from the indexed
   EPUB with chapter/CFI; frame or clip from video via `ffmpeg` at the subtitle
   timestamp; upload to the site. Can run after commit so the review page is not
   waiting on ffmpeg.

"Check media" is the transpose: one work's text as the cached prefix, every
trope description as the varying suffix.

Rechecks are the same passes with the existing instances excluded from "new
instance" output and included as targets for "new evidence". The worker never
proposes removals or changes (spec 7.4).

### 4.3 Calibration

The seed examples are the test. The review step reports, as the spec words it,
which seeds were found and at what score. If a seed scores under threshold, the
description needs work, and the page says so by showing the number, not by
adding a warning.

Keep every scan's proposal set (`proposals` table, 5.2) so that re-running after a
description edit can show what changed. This also gives the optional "rejected
suggestion" memory from spec 5 for free: a proposal the owner unchecked at
commit is a rejection, and a later recheck can list it last or skip it.

### 4.4 Writing rules enforcement

Spec section 9 goes into the system prompt verbatim. Add a post-check in the
worker: a small regex pass for the listed tells (em-dashes as connectors,
"not X but Y", process words like "added", "approved", "scan") that flags the
proposal for a rewrite call before it reaches the review page. Cheap, and it
stops the worst cases without hiding anything from you.

---

## 5. Data model

Spec section 5, with the changes below. Field names are mine where the spec
left them open.

### 5.1 Changes from the spec

- **Series.** Proposal: an instance attaches to exactly one *subject*, which is
  either a media item or a series (`subject_kind`, `subject_id`). A series is a
  named group with ordered members. Trope pages show a series instance once,
  under the series name. A member's media page shows series-level instances in
  the same list with a quiet "as part of Terra Ignota" lead-in. The library
  stays one row per log entry. The pipeline scans at series level when a series
  exists, merging member dossiers. This is "both, by inheritance" and avoids
  writing the same Dog Duo entry four times. Needs your yes (decision 4).
- **Notion id** on media items, for idempotent re-import. Site-only items have
  it null.
- **Proposals** table (above) so scans are reviewable and rejections are
  remembered.
- **Jobs**, **sessions**, **api_keys** for the plumbing.
- **Dossiers** keyed by subject, with `depth` and `built_at`.
- **Local sources** as their own table: path, kind (epub, video, subtitle,
  audio), indexed text location, duration or page count, indexed_at. One media
  item can have several (a season's episodes).
- **External ids** as rows (`site`, `external_id`, `url`, `score`, `score_label`)
  rather than a JSON blob, so the links line and the metadata refresh are
  queries.
- **Evidence** gets `file_path` (null for quotes), `width`, `height`,
  `duration_ms` and a `public` flag so a fair-use cap can be enforced per work
  without deleting anything.
- **`notable`** is an ordered join table, not an array column.

### 5.2 Tables (first cut)

```
media        id, notion_id?, title, type, creator, logged_date?, description,
             poster_path?, local_root?, rating_medium? … rating_effect?,
             created_at, updated_at
series       id, name, description
series_member series_id, media_id, position
trope        id, name, slug, description, created_at, updated_at
trope_seed   trope_id, title, media_id?            -- seeds as typed, resolved if matched
instance     id, trope_id, subject_kind, subject_id, who, text, prominence,
             verified, score?, origin, created_at, updated_at
notable      trope_id, instance_id, position
evidence     id, instance_id, kind, locator, content?, file_path?, width?,
             height?, duration_ms?, public, created_at
external_id  media_id, site, external_id, url, score?, score_label?
metadata     media_id, key, value                  -- seasons, episodes, aired, studio, genres, source
genre        media_id, genre                       -- for library filters
local_source id, media_id, kind, path, index_path?, length?, indexed_at?
dossier      subject_kind, subject_id, depth, body JSON, model, built_at
job          id, kind, payload, status, progress?, result?, error?, timestamps
proposal     id, job_id, trope_id, subject_kind, subject_id, score, prominence,
             who, text, evidence JSON, decision (pending|accepted|rejected)
session      id, created_at, expires_at, user_agent
api_key      id, name, hash, created_at, last_used_at
```

FTS5 virtual tables over `media.title`, `media.creator`, `trope.name`,
`trope.description`, `instance.text` for the header search.

### 5.3 Ratings

Average is the mean of filled axes, as the spec says, **pending** the Notion
formula check. The Notion connector exposes the formula only as an opaque
reference, so I could not read it from here. You need to open the property in
Notion and paste the formula (decision 8). If it differs, the importer computes
the Notion value and stores it; the site never recomputes.

---

## 6. Auth

Single owner, public read. Requirements: the same page serves both audiences;
mutations must be impossible for the public; the worker needs its own
credential; nothing should depend on a third-party identity provider.

### 6.1 Design

- `OWNER_PASSWORD_HASH` (argon2id) in the environment. No user table.
- `/login` form. On success, insert a `session` row and set `tl_session`:
  HttpOnly, Secure, SameSite=Lax, Path=/, 90 days, rotated on each login.
  `/logout` deletes the row.
- Middleware resolves the cookie to `locals.owner: boolean` on every request.
  Pages branch on it for controls; the public variant is the same component
  with the controls omitted, not a second template.
- Every Action and every mutating API route checks `locals.owner` (or a worker
  token) and returns 403 otherwise. This is the only line of defence that
  matters; hiding the buttons is cosmetics.
- CSRF: Astro's origin check for Actions and form posts, plus SameSite=Lax.
- Login rate limit: in-memory, 5 attempts per minute per IP, then a 60 s
  back-off. Enough for one owner.
- Owner-only pages (`/add/trope`, `/add/media`, `/recheck/…`, `/login` when
  already logged in) redirect anonymous visitors to the public page or 404.
- Worker: `api_key` table, token shown once at creation, stored hashed,
  `Authorization: Bearer`. Scoped to `/api/jobs*`, `/api/evidence`,
  `/api/export/*`. Owner session cookies are *not* accepted on those routes
  and the bearer token is not accepted on page Actions. Two credentials, two
  surfaces.
- Phase 6: passkey login via `@simplewebauthn/server` as a second method. The
  password stays as recovery.

### 6.2 Alternatives

**Cloudflare Access or Tailscale in front of an `edit.` hostname** with the
app trusting a header. Zero auth code, but the owner and public views become
different origins, every link has to know which host it is on, and the app
still has to trust a header it cannot verify without the Access JWT check,
which is auth code again. Not recommended.

**OAuth (GitHub login) with an allowlist of one.** Adds a dependency and a
redirect dance for no gain over a password plus passkey.

---

## 7. Cost estimates for the pipeline

Anthropic list prices as of 2026-10-19: Opus 5 $5/$25 per million tokens in/out,
Sonnet 5 $2/$10, Haiku 4.5 $1/$5. Batch API is half price. Token counts are
rough: a novel 100–150k, a TV season of subtitles 50–80k, a film 15–20k, games
and albums have little or no text of their own.

| Operation | Input tokens | Model | Cost |
|---|---|---|---|
| Metadata dossiers, all 778 works | ~2k × 778 ≈ 1.6M | Sonnet 5 | ≈ $3 once |
| Full dossiers, everything with local text (say 350 works) | ~90k × 350 ≈ 32M | Sonnet 5, batch | ≈ $35 once |
| Pass 1, one trope | ~1.5k × 778 ≈ 1.2M | Sonnet 5 | ≈ $2.50 |
| Pass 2, one trope, 30 candidates | ~100k × 30 ≈ 3M | Opus 5 | ≈ $15 (≈ $6 on Sonnet) |
| Check one new work against all tropes | one ~100k prefix cached, ~27 short suffixes | Opus 5 | well under $1 |
| Rebuild everything after a prompt change | all of the above | | ≈ $50 |

So adding a trope costs single-digit to low-double-digit dollars with Opus 5 on
pass 2. That is the step where quality shows on the page, so I would start
there and drop to Sonnet 5 only if the writing holds up. Rechecks cost the same
as the original scan minus already-associated works.

Latency for the interactive "Scan 778 entries": pass 1 is ~32 concurrent calls,
under a minute; pass 2 is ~30 concurrent long-context calls, one to three
minutes. The review page shows progress from the job row.

---

## 8. Phases

Each phase ends in something you can use. The acceptance line is what has to
be true before the next phase starts.

### Phase 0: decisions and scaffold (S)

- This document, the decisions in section 9, repo on GitHub.
- `web/` Astro project with the Node adapter, Drizzle, SQLite, one migration,
  the page frame (header, nav, search field, footer), fonts, colour tokens.
- `worker/` uv project skeleton with the HTTP client and a `ping` job.
- `justfile`, `compose.yml`, CI running typecheck, lint, build, pytest.

Acceptance: `just dev` serves an empty site with the right frame; CI is green.

### Phase 1: library (M)

- Notion importer: CSV export in, idempotent by Notion id, reports
  duplicates and near-duplicates (spec 8.1 lists them). Typos get fixed in
  Notion, not in the importer.
- Media page header only: poster (from Image Link when present), title,
  metadata line, description, rating mark, links line. No tropes yet.
- Library page: table, newest first, undated last, type and rating filters,
  "Show all", rating breakdown columns, sort by full date.
- Rating mark component with the bar rules from spec 4.
- Header search: FTS5 over titles and creators, a plain results page.
- Public read-only. No auth yet; the site is not exposed.

Acceptance: all 778 entries imported and browsable; library sorts and filters
match spec 6.4; rating bars match the shade and height rules.

### Phase 2: tropes, manual authoring, auth (L)

- Auth as in section 6 (password, sessions, middleware, 403 on mutations).
- Tropes index, trope page, media page trope list, both in the margin layout
  with the 1100px collapse.
- Text pipeline: `[[links]]`, `||spoilers||`, restricted Markdown.
- Inline editing: description edit, instance edit panel (prominence, text,
  pin as notable, remove), verification toggle, add-media-to-trope and
  add-trope-to-media with autocomplete, manual evidence (quotes by hand).
- Series table and the subject model from 5.1.
- Seed content: the 10 Mind/Machine/Divine/Animal tropes and the 16
  brainstormed ones from spec 10, with the Dog Duo and Pantheon instances
  entered by hand so the pages have real content to judge the layout on.
- Public variant: same components, controls off, verification marks hidden.

Acceptance: you can author a trope end to end without the pipeline; the public
Dog Duo page matches the `PublicTropeMargin` artboard; anonymous requests to
every Action return 403 (tested).

### Phase 3: matching on cheap inputs (L)

- Job API and worker loop (3.2).
- Your writing as a source: midden search with quoted titles and the API key,
  and the annual review posts. Stored per work as input to dossiers.
- Metadata-depth dossiers for all works.
- Pass 1 and pass 2 over dossiers (no local text yet). Pass 2 can still write
  `who` and text; evidence is quotes only if the dossier has them, else none.
- Add trope flow (describe, scan, review, commit), add media check, recheck
  trope, recheck media, all producing proposals and committing to instances.
  Scores shown only on those pages.
- Writing-rules post-check (4.4).
- Calibration line on the review page.

Acceptance: "Scan 778 entries" for Dog Duo finds the known seeds with
reportable scores and proposes at least the SPY x FAMILY and Owl House rows
from the mock, or we learn why not and tune the prompt.

### Phase 4: external metadata and posters (M)

- `lookup_media` job: TMDB (films, TV, posters), Jikan (MAL), Wikipedia
  summary and infobox, TVDB, Open Library, Steam store API, Letterboxd and
  Metacritic and Rotten Tomatoes only where an API or clean page exists. IMDb
  ratings from the public datasets dump rather than scraping, if wanted.
- Poster fetch and resize for the ~600 entries without an Image Link.
- Genres into the library filters; metadata line and links line fully
  populated.
- Add-media step 2 ("confirm what was found") built on this job.

Acceptance: Pantheon and Metallic Rouge pages show the values from the mock
without hand entry; library has a working genre filter.

### Phase 5: local media and evidence (XL)

- Library layout discovery with you: paths, naming, where subtitles live,
  Plex metadata if useful.
- `index_local`: EPUB to text with chapter and CFI map; video subtitle
  extraction with ffmpeg, Whisper fallback; store indexes on the worker side,
  report locations to the site.
- Full-depth dossiers for indexed works.
- Pass 2 reads indexed text; evidence locators become real.
- `extract_evidence`: quotes with locators, frames at timestamps, clips with
  ranges, upload to the site, render in the margin column.
- Recheck flows propose new evidence for existing instances.

Acceptance: a Gideon the Ninth quote with a chapter locator and a Pantheon
frame with an episode timestamp appear on the live Dog Duo and Pantheon pages
from the pipeline, not by hand.

### Phase 6: public hardening (M)

- Fair-use caps (decision 6): quote length, frames per work per trope, whether
  clips are public at all. Enforced by the `public` flag, never by deletion.
- Rate limiting on search and on anonymous page views; robots and OG tags;
  cache headers on evidence files.
- Passkey login.
- Backups: nightly SQLite snapshot plus the evidence directory to the Hetzner
  box or R2.
- Narrow-screen spacing pass (spec 3 says it needs one).
- Tumblr mention count: show as a link only until relevance filtering exists.

Acceptance: the site is reachable publicly, survives a crawler, and you can log
in from a phone with a passkey.

### Deferred, by design

Collections, review queue, drafts, related-tropes lists, "shares the most
tropes with", confidence badges, the show-all-spoilers toggle. Spec 11 lists
them as rejected; they do not come back without a new reason.

---

## 9. Decisions needed

Numbered so you can answer by number.

1. **Stack.** Astro 7 + SQLite + Node container, Python worker, as in section 2.
   Or Cloudflare Workers + D1 + R2 for the site.
2. **Hosting.** Which box for the site: the homelab migration target, a small
   VPS, or Cloudflare. The worker runs next to the media regardless.
3. **Repo visibility.** I created `wasabipesto-bot/tropes` as private. Flip to
   public when you want; the code has no secrets by design.
4. **Series model.** "Both, by inheritance" as in 5.1, or instances per book.
5. **Notion sync direction.** One-way Notion to site, re-runnable, Notion owns
   title, type, creator, ratings, date, links. Site-added items stay site-only.
   Or should the site write back to Notion?
6. **Evidence on public pages.** Proposed caps: quotes up to ~100 words, up to
   three frames per work per trope, clips owner-only until decided otherwise.
   This is a policy choice, not legal research.
7. **Models and provider.** Anthropic direct with the split in 2.4, or
   OpenRouter. Opus 5 for pass 2 to start.
8. **Notion Average Rating formula.** Please paste it; the connector cannot
   read it.
9. **Worker language.** Python as proposed, or TypeScript to share types.
10. **Typos in Notion.** Fix the titles listed in spec 8.1 before the first
    import, or import as-is and fix later (the importer keys on Notion id, so
    either order works).

Content questions from the spec (DAN DA DAN imagery, local library layout) come
up in Phases 2 and 5 and do not block starting.

---

## 10. Risks

- **Astro 7 drift.** My knowledge of Astro is older than 7.x. Budget time in
  Phase 0 to read the current docs rather than guess APIs.
- **Pass 1 recall on dossiers.** If metadata-depth dossiers miss tropes that
  only show in the text (likely for imagery-based ones like Dog Duo), Phase 3
  results will look thin until Phase 5. The seeds will show this honestly.
- **Evidence extraction is the long pole.** Spec 7.2 already accepts this.
  Phase 5 is the only XL phase and it depends on your library layout.
- **Metadata scraping friction.** IMDb blocks, Goodreads is hostile, Letterboxd
  has no public API. Phase 4 should prefer the APIs that exist and accept gaps.
- **SQLite single writer.** Fine as long as the worker stays behind the HTTP
  API. The temptation to let the worker open the file directly is the thing to
  resist.
