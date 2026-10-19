# Trope Log

A personal TVTropes-style catalogue built on a media log. Each trope has a page
describing it and listing every logged work where it appears; each work has a
page listing its tropes, ratings and links. Associations are proposed by a
language model that reads the log and the source material, then verified by hand.

Status: Phase 0 (scaffold). The site serves its page frame and a health
endpoint; nothing is imported yet. See `docs/ROADMAP.md` for the phases.

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
```

The database path comes from `DATABASE_PATH` (default `./data/tropes.db`);
migrations in `web/drizzle/` apply at startup.

License: MIT. Source Serif 4 is bundled under the SIL Open Font License, see
`web/public/fonts/LICENSE.md`.
