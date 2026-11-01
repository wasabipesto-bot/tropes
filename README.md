# Trope Log

A personal TVTropes-style catalogue built on a media log. Each trope has a page
describing it and listing every logged work where it appears, with the quotes,
frames and clips that show it; each work has a page with its tropes, ratings,
links, and the openings and title sequences worth watching. Associations are
proposed by a language model that reads the log, the works' own text and
frames of their footage, and are verified by hand before they count.

Live at https://tropes.wasabipesto.com. MIT licensed; Source Serif 4 is bundled
under the SIL Open Font License (`web/public/fonts/LICENSE.md`).

## How it works

- **The log.** A Notion database of everything watched, read and played is the
  source of truth for what exists. The worker syncs it every fifteen minutes;
  new entries are looked up, described and checked automatically.
- **Identity and metadata.** Each entry is matched to a Wikidata item (the
  owner's Notion link wins when there is one), then enriched from TMDB,
  MyAnimeList, Steam, Open Library, MusicBrainz, iTunes, IMDb, Rotten
  Tomatoes, Metacritic and Goodreads: details, scores, genres, links, a poster.
- **Text.** A second worker next to the media files extracts subtitles (sidecar,
  embedded, OpenSubtitles, Whisper as the last resort) and book text, and makes
  a contact sheet of frames per episode which the model reads into "visual
  notes". Fandom articles and the owner's Tumblr posts about a work join in.
- **Dossiers.** For every work the model writes an internal dossier — characters,
  settings, arcs, motifs, themes, notable scenes with locators — from
  everything above. Dossiers are public at `/media/<id>/dossier` and say what
  they were built from.
- **Scans.** A new trope is a name, a description and a few examples. Pass 1
  scores every dossier; pass 2 reads the candidates' text, writes the entry
  and copies exact quotes, which are checked verbatim. Frames are grabbed at
  quoted moments; for tropes marked visual the model looks at them before
  proposing. Proposals wait on `/review`.
- **Verification.** The owner accepts, edits or rejects. Anything the owner
  has not looked at is marked. Adding an association by hand is one field:
  a title and a note, and the model drafts the rest.

## Layout

- `web/` — the site: Astro 7 in server mode, Node adapter, one SQLite file via
  better-sqlite3 and Drizzle. The only process that writes the database.
  Migrations in `web/drizzle/` apply at startup.
- `worker/` — the pipeline: Python, `uv`. Two roles from one package: the
  **model worker** (talks to OpenRouter and the metadata sources) and the
  **media worker** (set `TROPES_MEDIA_ROOT`; it then takes only the file jobs
  — indexing, subtitles, frames, sheets, Whisper). Both talk to the site over
  HTTP with an API key and never open the database. Documented in
  `worker/README.md`.
- `ops/` — the backup container and the media worker's systemd unit.
- `compose.yml` — production: site, model worker, backup.

## Running it

```
just setup            # npm ci + uv sync
just dev              # site on http://127.0.0.1:4321 with live reload (just dev <host> to expose it)
just ci               # type-check, lint, test, build
just worker           # the model worker against the dev site (needs .env)
just api-key <name>   # mint a worker's bearer token, once per worker
just queue <kind> '<json>'   # put a job on the queue by hand
```

Configuration is one `.env` at the repo root (`.env.example` lists everything):
OpenRouter and Notion keys, the metadata sources' keys, the owner password hash
(`just hash-password 'secret'`), `SITE_ORIGIN`, fair-use caps and rate limits,
`TROPES_MEDIA_ROOT` and the OpenSubtitles login on the media host, the
backup target.

Astro notes that bit us: one background dev server per project (`astro dev
--background`, `astro dev stop/status/logs`); form actions build their input
from the zod shape, so repeated fields are arrays, a blank field arrives as
`null`, and an unticked checkbox is absent; cookies set in an API route attach
to the returned `Response`; the dev server's Vite only admits IPs and
`*.localhost` as hosts.

## Deployment

The site and the model worker run on one host in Docker Compose from images
that CI publishes to GHCR on every push to `main`
(`ghcr.io/wasabipesto-bot/tropes-{web,worker,backup}`, tags `main` and
`sha-<commit>`). The media worker runs on the host that holds the files.

On the server, once:

```
git clone --depth 1 https://github.com/wasabipesto-bot/tropes ~/tropes && cd ~/tropes
cp .env.example .env            # fill in secrets; set TROPES_PORT, SITE_ORIGIN, TROPES_TRUSTED_PROXY=1 behind a tunnel or proxy
mkdir -p data worker-data ops/ssh   # ops/ssh: the storage box key, config and known_hosts (see ops/ssh/README.md)
docker compose pull && docker compose up -d
```

Then from any checkout, `just on <host> deploy` pulls the images and restarts
what changed; `just on <host> health`, `logs web`, `logs worker`, `backup`.
Data lives in `data/` (database, posters, evidence, sheets, texts) and
`worker-data/` (the owner's linked sources, the worker's text and lookup
caches); `just seed-data <host>` copies both from a development checkout before
the first start. An extra compose file (`compose.timbre.yml`) publishes the
port on the Tailscale address so the media worker can reach the site; enable
it with `COMPOSE_FILE=compose.yml:compose.timbre.yml` in `.env`.

The media worker: `ops/tropes-media-worker.service` as a user unit, `uv sync
--extra whisper` for Whisper, `TROPES_SITE_URL` pointing at the site's
Tailscale address, its own API key. It re-indexes the disk weekly.

**Backups.** The backup container snapshots the database nightly at 03:30 UTC
(`sqlite3 .backup`, gzipped, 14 daily and 8 weekly kept) and rsyncs the
snapshots with evidence, posters, texts and the owner's sources to the Hetzner
storage box; contact sheets and the lookup cache are regenerable and are not
copied. Restore = stop, drop the `.sqlite` back as `data/tropes.db`, start.

**Hardening.** Fair-use caps for visitors (quotes to 100 words, 10 frames per
work per trope, clips to 30 seconds — over-cap evidence stays, owner-only);
rate limits per address (30 searches, 120 pages, 60 API calls a minute);
`robots.txt`, OG tags and canonical links from `SITE_ORIGIN`; passkeys for the
owner with the password as fallback.

## Read API

Public, no key, JSON, CORS open, cached five minutes; spoilers stay in
`||bars||` as on the pages.

- `GET /api/v1/tropes` — every trope with its instance count.
- `GET /api/v1/tropes/<slug>` — a trope with every instance and its evidence
  (quotes, frames and clips as URLs). Old slugs resolve.
- `GET /api/v1/media` — the library.
- `GET /api/v1/media/<id>` — a work with its links, genres, series, instances
  and dossier.

Everything under `/api/export`, `/api/jobs`, `/api/sources`, `/api/evidence`,
`/api/dossiers`, `/api/videos` and `/api/import` is for the workers and needs
an API key.

## History

Built October 2026 in phases: the site and library import; metadata and
posters; the matching pipeline and review; local media (subtitles, frames,
Whisper, visual notes); public hardening; openings and title sequences from
AnimeThemes, Art of the Title and TMDB; noted examples and one-field
associations. Moved to its own server in November 2026.
