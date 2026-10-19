# tropes-worker

The pipeline half of Trope Log. It runs wherever the local media lives, claims
jobs from the site over HTTP, does the slow work (model calls, metadata lookup,
text extraction, frame and clip cutting) and posts results back. It never opens
the site's database.

Phase 0 ships the client and a `ping` command. Jobs arrive in Phase 3.

```
uv sync
uv run tropes-worker ping --site http://127.0.0.1:4321
```

Configuration is by environment variable: `TROPES_SITE_URL`, `TROPES_API_TOKEN`.
