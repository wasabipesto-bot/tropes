# Trope Log

A personal TVTropes-style catalogue built on a media log. Each trope has a page
describing it and listing every logged work where it appears; each work has a
page listing its tropes, ratings and links. Associations are proposed by a
language model that reads the log and the source material, then verified by hand.

Status: Phases 0 to 3 built. Library, media pages, search, tropes with
instances and evidence, owner login and inline editing, and the matching
pipeline: a worker builds a dossier per work, scans the library for a new
trope, checks a work against every trope, and the owner reviews proposals
before anything is saved. External metadata (Phase 4) is next. See
`docs/ROADMAP.md`.

## Layout

- `web/`: the site. Astro 7 in server mode, Node adapter, one SQLite file via
  better-sqlite3 and Drizzle. The only process that writes the database.
- `worker/`: the pipeline. Python, run with `uv`, next to the media library.
  Talks to the site over HTTP and never opens the database.
- `docs/`: `SPEC.md` (design handoff), `ROADMAP.md` (plan and decisions),
  `notes/` (verified reference notes), `canvas/` (design artboards).

## Run it

```
just setup     # npm ci + uv sync
just dev       # site on http://127.0.0.1:4321 with live reload
just ci        # type-check, lint, test, build
just up        # docker compose, site on 127.0.0.1:4321, data in ./data
just ping      # worker asks the site for its health
just api-key ivory-worker   # mint the worker's bearer token, once
just worker    # run the pipeline worker (needs OPENROUTER_API_KEY in .env)
```

The worker is documented in `worker/README.md`. Text sources for works live
under `data/sources/` and are registered with `just link-sources`.

The database path comes from `DATABASE_PATH` (default `./data/tropes.db`);
migrations in `web/drizzle/` apply at startup.

License: MIT. Source Serif 4 is bundled under the SIL Open Font License, see
`web/public/fonts/LICENSE.md`.

## Importing the log

Export the Notion "Media Log" as CSV and run `just import path/to/export.csv`.
Re-running is safe: rows match by Notion id when the file has one, otherwise by
title and type, and only Notion-owned fields (title, type, creator, ratings,
date, links) are overwritten. Add `--dry-run` to see what would change.

## Owner login

The site is public and read-only; editing needs the owner session. Put a
password hash in `web/.env` (or the container's environment):

```
just hash-password 'your password'      # prints OWNER_PASSWORD_HASH=…
```

Then log in at `/login`. Sessions last 90 days. There is one owner and no
user table by design.

## Seed content

`web/seed/tropes.json` holds the starting tropes, series and instances.
`just seed` loads whatever is not already present; `just seed --replace`
reloads tropes that exist, replacing their instances.

## Backups

`just backup` snapshots the database with `VACUUM INTO` (safe while the site
runs), tars the evidence directory, keeps the newest 14 of each in
`backups/`, and rsyncs that directory to `TROPES_BACKUP_REMOTE` (default
`braize:tropes-backups`). Set the variable empty to skip the copy.
