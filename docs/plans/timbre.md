# Proposal: Trope Log on timbre

2026-11-01. The site and the model worker move to timbre and run as a
long-lived service; the media worker stays on celebrimbor; the repo stays
on ivory for reference and feature work. Migration waits for the nice
numbers performance-history work on timbre to finish.

## Where things stand

ivory's dev server stopped around 2026-10-30 12:35 (the last database
write); the worker kept polling a dead port. The data is intact: integrity
check clean, 783 works, 350 associations, 793 dossiers, all jobs finished.
Nothing has run since, which is fine — nothing was scheduled to.

Data on ivory today: database 46 MB; posters 106 MB; evidence 2 MB; contact
sheets 1.9 GB; extracted texts 221 MB; your linked sources 76 MB; the
worker's text cache 436 MB and lookup cache 847 MB (both regenerable). About
2.8 GB to move, 3.7 with the caches.

timbre today (read-only look): 8 cores, 15.6 GB RAM with 6 GB free, 139 GB
of disk free, Tailscale 100.117.226.30, tumblr-search in Docker Compose
(images from GHCR, built by CI), public ingress through a Cloudflare
Tunnel (`cloudflared` on the host), port 4321 already taken by
tumblr-search's frontend.

## Target layout on timbre

One Compose project, `~/tropes` (a shallow clone for the compose file and
`.env`; the code arrives as images):

| Service | Image | Notes |
|---|---|---|
| `web` | `ghcr.io/wasabipesto-bot/tropes-web:main` | Astro node server; `./data:/app/data` (db, posters, evidence, sheets, texts); listens on `127.0.0.1:4330` and `100.117.226.30:4330`; `/api/health` healthcheck; 1 GB memory limit |
| `worker` | `ghcr.io/wasabipesto-bot/tropes-worker:main` | the model worker; `TROPES_SITE_URL=http://web:4321`; `./worker-data:/data` for sources, text cache, lookup cache; 2 GB memory limit; restarts on failure |
| `backup` | small image with sqlite3, rsync, ssh | nightly: `.backup` snapshot of the database, 14 daily + 8 weekly, rsync of db/posters/evidence/sources/texts to braize (`tropes/`), same layout the ivory script used |

Outside Compose:

- **Cloudflare Tunnel**: one ingress rule, `tropes.wasabipesto.com →
  http://localhost:4330`, plus the DNS record (`cloudflared tunnel route dns
  <tunnel> tropes.wasabipesto.com`). Because the tunnel terminates TLS, the
  site gets `SITE_ORIGIN=https://tropes.wasabipesto.com` and
  `TROPES_TRUSTED_PROXY=1` (visitor address from `CF-Connecting-IP`).
- **Media worker on celebrimbor**: unchanged code; `.env` gets
  `TROPES_SITE_URL=http://100.117.226.30:4330` (timbre over Tailscale) and
  keeps its API key — the key lives in the database, which moves. One
  restart.
- **ivory**: the dev server stays off; the worker service is removed so two
  model workers never run against the live site. Feature work uses
  `DATABASE_PATH=./data/dev.db` against a snapshot copy, and ships through
  CI → GHCR → `just on timbre deploy`, the same path tumblr-search uses.

## Code changes (small, all in the repo)

1. `worker/Dockerfile` (python 3.12-slim + uv; the model worker needs no
   ffmpeg or Whisper) and a GitHub Actions workflow that builds `tropes-web`
   and `tropes-worker` to GHCR on every push to `main` (tags `main` and the
   commit SHA). The repo is public, so GHCR pulls need no login.
2. `compose.yml`: the three services above with image tags, the two port
   bindings, healthchecks, memory limits, `env_file: .env`, and the worker's
   data paths via the env vars that already exist (`TROPES_SOURCES_DIR`,
   `TROPES_TEXT_CACHE_DIR`, `TROPES_LOOKUP_CACHE_DIR`).
3. `ops/docker/backup.Dockerfile` + `backup.sh` adapted to run inside the
   container (sqlite3 `.backup` instead of the node snapshot script; the
   braize key mounted read-only). The host-side systemd timer goes away.
4. `justfile`: an `on host recipe` runner like tumblr-search's; `deploy` on
   the host = `docker compose pull && docker compose up -d && just health`;
   a `seed-data` recipe that rsyncs ivory's data over Tailscale for the
   cutover.
5. `/jobs` shows when each worker last claimed (the api_key rows already
   record it) so a dead worker is visible without a shell.
6. `.env.example` gains the timbre values; `README` gets a "Running on
   timbre" section; the Phase 6 plan's go-live notes point here.

No schema changes; no behaviour changes for visitors.

## Cutover (about an hour, mostly waiting on rsync)

1. CI builds the images (step 1 above merged).
2. On timbre: clone, write `.env` from ivory's (secrets copied by hand:
   OpenRouter, Notion, TMDB, MAL, OpenSubtitles, Midden, the password
   hash, the API token), `docker compose pull`.
3. Freeze ivory: worker already stopped; take a snapshot of the database.
4. `just seed-data timbre`: rsync `web/data` (db snapshot, posters,
   evidence, sheets, texts), `data/sources`, `data/text` into `~/tropes/`.
   The lookup cache is skipped (it refills).
5. `docker compose up -d`; `just health`; log in with the password; check
   `/jobs` and one media page with sheets and a video.
6. Tunnel rule + DNS; check `https://tropes.wasabipesto.com` end to end
   (robots, OG tags, a 429 from the rate limiter).
7. You change celebrimbor's `TROPES_SITE_URL` and restart the media worker;
   I queue a `ping` and a one-work `index_local` to see both workers claim.
8. Backup container's first run; verify the files on braize.
9. Register a passkey from your phone (the dev-origin one is void).
10. ivory: remove the worker unit, leave the repo.

## Ops notes

- Disk: ~3 GB now, growing by sheets and texts as you log things —
  perhaps 100–200 MB a month. The nightly backup carries about 400 MB
  (sheets excluded as regenerable).
- Memory: web ~300 MB, worker ~500 MB in steady state; the worker peaks
  when it reads a long text (one text at a time now). Limits catch a
  regression instead of taking the host down.
- The weekly disk re-index lives on celebrimbor and keeps posting to
  wherever `TROPES_SITE_URL` points; nothing else is scheduled on the
  server side except the Notion sync inside the worker.
- The Notion integration still sees the whole Garden workspace; the worker
  reads only the Media Log, as before.
- Rate limits are in-process; one web container means one bucket set,
  which is what we want.
- A heartbeat check from outside (any uptime pinger hitting
  `/api/health`) is the one thing not in the repo; your call where.
- Rollback: ivory's data stays as a frozen copy until you say the move is
  settled; pointing celebrimbor back is one env line.

## Open questions

1. Images from GHCR (CI, no build load on timbre) as proposed, or build on
   timbre like the current `just up`?
2. Backup key: copy ivory's braize key to timbre, or a new key added to the
   storage box?
3. Anything else that should share the box with tumblr-search and the nice
   work — any memory or CPU cap you want on the worker beyond 2 GB?
