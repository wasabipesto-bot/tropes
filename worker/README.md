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

Results carry `usage` (calls, tokens, cost in USD as OpenRouter reports it)
and `warnings`; the review pages show both.

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
