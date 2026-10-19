# Phase 3 plan: the matching pipeline

Written 2026-10-19 for approval before any of it is built. It breaks Phase 3
of `ROADMAP.md` into tasks, each with scope, approach, the decisions it needs
(with a recommendation), and implementation detail with the tradeoffs. The
bias throughout is toward the fewest moving parts that still do the job:
one SQLite file, one HTTP contract, one worker process, prompts as plain
files, no queueing software, no client-side framework.

What Phase 3 delivers: adding a trope scans the library and proposes
instances; adding or rechecking a work checks it against every trope;
rechecks propose additions only; the owner reviews and commits. Evidence is
quotes from text sources where a text source exists. Frames, clips and the
local media library are Phase 5; external metadata and the real "look it
up" step are Phase 4.

---

## 0. Shape of the system after Phase 3

```
site (Astro, SQLite)                       worker (Python, same host for now)
  jobs, proposals, dossiers, api keys  <──  claims jobs over HTTP with a bearer token
  review pages poll job status         ──►  posts progress and results
  commit creates instances + evidence       reads text sources from data/sources
                                            calls OpenRouter (DeepSeek V4.1 Flash)
```

The worker never opens the database. The site never calls the model. The
owner's browser never talks to the worker.

---

## 1. Tasks

Order is dependency order. Sizes are relative.

| # | Task | Size | Depends on |
|---|---|---|---|
| T1 | Job queue, proposals and the worker API | M | |
| T2 | Worker runtime: loop, config, model client, structured output | M | T1 |
| T3 | Sources and dossiers | M | T2 |
| T4 | Pass 1 and pass 2: scan a trope, check a work | L | T3 |
| T5 | Review pages: add trope, add media, recheck trope, recheck media | L | T1 (UI can be built against hand-made jobs before T4) |
| T6 | The owner's writing as a source | S | T3 |
| T7 | Calibration line and an eval command | S | T4 |
| T8 | Operations: keys, running the worker, retries, cost logging, docs | S | T2 |

---

## T1. Job queue, proposals and the worker API

**Scope.** Two tables and a handful of endpoints so the site can hand work to
the worker and get results back, plus an API key the worker presents.

**Approach.** `job` and `proposal` tables in the existing SQLite file (schema
in `ROADMAP.md` 5.2, refined below). The site writes a job row when the owner
presses "Scan 778 entries"; the worker polls for unclaimed jobs, marks one
running, posts progress, posts a result; the review page polls the job row.

**Tables.**

```
job        id, kind, payload JSON, status (queued|running|done|failed|cancelled),
           progress JSON ({done, total, note}), result JSON, error,
           created_at, claimed_at, heartbeat_at, finished_at, usage JSON
proposal   id, job_id, trope_id, subject_kind, subject_id, score, prominence,
           who, text, evidence JSON, kind (instance|evidence), target_instance_id?,
           decision (pending|accepted|rejected), created_at
dossier    subject_kind, subject_id, depth (knowledge|text), body JSON,
           model, built_at, source_hash   (primary key subject_kind+subject_id)
api_key    id, name, hash, created_at, last_used_at
```

`usage` on the job holds token counts and the model id, summed by the
worker; that is the whole cost log (decision D8).

**Endpoints.** All under `/api/`, all JSON. Bearer token for the worker; the
owner session for the two the review pages call.

| Route | Who | Purpose |
|---|---|---|
| `POST /api/jobs/claim` | worker | atomically take the oldest queued job of the kinds it handles; returns the job or 204 |
| `POST /api/jobs/:id/progress` | worker | `{done, total, note}`; also the heartbeat |
| `POST /api/jobs/:id/result` | worker | final payload; the site writes proposals and dossiers from it in one transaction |
| `POST /api/jobs/:id/fail` | worker | error text; status → failed |
| `GET /api/export/tropes` | worker | every trope with description, seeds, existing instance subjects (for "additions only") |
| `GET /api/export/subjects` | worker | every media item and series with the fields a dossier needs, plus dossier status and text-source paths |
| `GET /api/dossiers/:kind/:id` | worker | existing dossier, or 404 |
| `GET /api/jobs/:id` | owner | status and progress for the review page's poll |

**Decisions.**

- **D1. Polling, not push.** The worker short-polls `claim` every 2 s when
  idle; the review page polls `GET /api/jobs/:id` every 2 s until done.
  Recommendation: polling. Server-sent events or websockets save nothing at
  this scale and add a long-lived connection to debug.
- **D2. One worker, one job at a time.** Parallelism lives inside a job
  (concurrent model calls), not across jobs. Recommendation: yes. It keeps
  rate limiting and progress reporting trivial. A second worker can be
  added later by making `claim` atomic, which it will be from day one
  (`UPDATE … WHERE status='queued' … RETURNING`).
- **D3. Stale jobs.** A running job with no heartbeat for 10 minutes goes
  back to queued once, then fails. Recommendation: yes, in the claim query
  itself, so there is no reaper process.
- **D4. Job payloads and results are opaque JSON** validated by zod on the
  site and pydantic in the worker. Recommendation: yes. The alternative, a
  column per field, means a migration per prompt change.

**Tradeoffs.** SQLite as a queue is fine for one worker and a few jobs a day.
It would not be fine for many workers hammering `claim`; that is not this
project. Keeping dossiers in the site database (rather than worker-local
files) costs an endpoint but means backups cover them and a second worker
host sees them.

**Acceptance.** A job created by hand with `sqlite3` is claimed by the
worker's `ping`-style command, progressed, and finished; the owner page
shows each state; a worker with a bad token gets 401; a stale job is
reclaimed.

---

## T2. Worker runtime

**Scope.** The loop that claims and runs jobs, configuration, the model
client, and the way structured output is requested and checked.

**Approach.** `tropes_worker/` gains `runner.py` (claim loop), `llm.py`
(one `complete()` function), `schemas.py` (pydantic models for every prompt
output), `prompts/*.md` (one file per prompt, plain markdown with `{{}}`
slots), and `jobs/` (one module per job kind, each a function
`run(job, ctx) -> result`). `tropes-worker run` starts the loop;
`tropes-worker run --once` claims one job and exits, which is what tests and
manual debugging use.

**Decisions.**

- **D5. Model client.** The `openai` Python package pointed at OpenRouter's
  base URL, versus raw `httpx`. Recommendation: the `openai` package. It
  handles retries, streaming and timeouts, OpenRouter speaks its wire
  format, and switching models or providers is a config change. The cost is
  one dependency.
- **D6. Structured output.** Ask for JSON in the prompt, parse, validate with
  pydantic, and retry once with the validation error appended. Do not rely
  on provider-side JSON schema enforcement. Recommendation: as stated.
  OpenRouter's structured-output support varies by model and route; a
  client-side check works everywhere and the failure mode is visible.
- **D7. Concurrency.** `asyncio` with a semaphore, default 8 concurrent
  model calls, configurable. Recommendation: 8. Pass 1 is 32 calls, pass 2
  up to 60; at 8-wide a scan finishes in a minute or two.
- **D8. Cost logging.** Sum `usage` from every response into the job's
  `usage` field (prompt tokens, completion tokens, cached tokens, model,
  call count). No separate table, no per-call log. Recommendation: this.
  The question "what did that scan cost" is answered from the job row; a
  per-call ledger is more to maintain than it is worth at cents per scan.
- **D9. Configuration.** Environment variables only: `TROPES_SITE_URL`,
  `TROPES_API_TOKEN`, `OPENROUTER_API_KEY`, `TROPES_MODEL`
  (default `deepseek/deepseek-v4.1-flash-1017`), `TROPES_LLM_CONCURRENCY`,
  `TROPES_SOURCES_DIR`. Recommendation: this, read once at startup into a
  frozen `Settings` dataclass. No config file.
- **D10. Sampling.** One temperature for everything, 0.3. Recommendation:
  start there and tune with the eval (T7) rather than guess per prompt.

**Tradeoffs.** Prompts as files rather than Python strings means they can be
read and edited without touching code, and diffs show prompt changes
clearly; the cost is a tiny template step. pydantic adds a dependency but
removes a class of silent bad-output bugs.

**Acceptance.** `tropes-worker run --once` completes a `ping` job end to
end; a fixture test runs each prompt's parser against saved good and bad
outputs without the network.

---

## T3. Sources and dossiers

**Scope.** Reading text sources that already exist as files, and building
the per-work dossier that pass 1 reads.

**Approach.**

*Text sources.* `data/sources/sources.json` (written today) lists what
exists. The worker gets a `sources.py` that turns a path into plain text
with chapter markers: `.txt` as-is (Gutenberg headers stripped), `.epub`
via `ebooklib` plus an HTML-to-text pass, chapters from the spine. Output is
cached as `data/text/<subject>.txt` keyed by file hash. The site learns
about a source through the existing `local_source` table (`kind='text'`,
`path`), which `GET /api/export/subjects` returns. A small `just link-source
<title> <path>` recipe writes that row so no UI is needed yet.

*Dossiers.* Built once per subject by a `build_dossier` job, stored in the
site database. Two depths:

- `knowledge`: from the log entry (title, type, creator, year, your
  description if any), your own writing about it (T6), and the model's own
  knowledge of the work, with an explicit instruction to say so when it
  does not know the work.
- `text`: the same prompt plus the full text when a text source exists.
  A 1M-token context takes a whole novel; no chunking in Phase 3.

Dossier body (JSON, 1–2k tokens): `summary` (one paragraph), `characters`
(name, role, descriptors, relationships), `settings`, `arcs` (with
chapter or episode locators when text was read), `motifs` (recurring
imagery, objects, phrases), `themes`, `notable_scenes` (with locators),
`known: strong|partial|none`, and `depth`. Rebuilt when the source hash or
the prompt version changes.

**Decisions.**

- **D11. Allow the model's own knowledge as a dossier source.**
  Recommendation: yes. Most of the 776 works are well known and the model's
  knowledge of them is far better than title plus creator. The risk is
  confident nonsense about obscure works (Foreach, Floornight, a small
  album); mitigations are the `known` field, grounding on text when it
  exists, the owner's verification mark, and never showing dossiers on the
  site. The alternative, metadata-only dossiers, would make pass 1 nearly
  blind until Phase 4 and 5.
- **D12. Dossiers live in the site database.** Recommendation: yes, see T1
  tradeoffs.
- **D13. Phase 3 reads text files that are already on disk; it does not
  find media.** Plex paths, subtitles, frame sampling stay in Phase 5.
  Recommendation: yes. Today's sources (four novels, ten classics, five web
  serials, three Crystal books, qntm's three) are enough to build and tune
  the text path.
- **D14. Series dossiers.** A series dossier is built from its members'
  dossiers (and texts, when present) in one call, so a scan sees Terra
  Ignota once. Recommendation: yes; instances already attach to series.

**Tradeoffs.** Building 776 knowledge dossiers up front costs about a dollar
and twenty minutes at 8-wide and makes every later scan fast; building
lazily on first scan saves nothing worth having. Recommendation: a
`build_dossiers` job that fills whatever is missing, run once after T3 and
again whenever the prompt version bumps.

**Acceptance.** Dossiers exist for every subject; the ones with text
sources are `text` depth; spot checks on Lent, Unsong and a well-known film
read as accurate; a dossier for Foreach says it is not known.

---

## T4. Pass 1 and pass 2

**Scope.** The two prompts and the orchestration for the three job kinds
that produce proposals: `scan_trope` (add trope and recheck trope),
`check_subject` (add media and recheck media), and `build_dossier` from T3.

**Approach.**

*Pass 1, per trope.* Batches of 25 dossiers per call; input is the trope
description (verbatim, it is the prompt), the seed titles, and the batch;
output is `[{subject, score 0–1, reason ≤ 20 words}]`. Seeds are always
carried forward regardless of score so calibration can be reported.
Candidates for pass 2: everything scoring ≥ 0.3, capped at 60 by score,
plus seeds, minus subjects already associated (for rechecks) and subjects
previously rejected for this trope (D17).

*Pass 2, per candidate.* Input: trope description, seeds, the writing rules
from `SPEC.md` section 9 verbatim, the candidate's dossier, and its full
text when there is one. Output: `score`, `prominence`, `who`, `text`,
`evidence` as quote candidates (`content`, `locator`) only when a text was
read, else empty. The prompt says plainly that no instance is also a valid
answer. Text is checked by the writing post-check (below) and sent back for
one rewrite if it trips.

*Check subject, per work or series.* One call: the subject's dossier and
text as the prefix, then every trope's description and seeds; output is
one entry per trope with the same shape as pass 2, most of them "no". For
rechecks, tropes already attached are asked only for new evidence (text
sources only), and the output is split into "new tropes" and "new
evidence".

*Writing post-check.* A regex list in `writing_check.py` for the tells in
spec section 9: em-dash connectors, "not X but Y", process words (added,
approved, scan, verified, weak match, kept), rule-of-three closers, and
the `||` balance. A trip means one rewrite call with the specific
complaint; a second trip is accepted and flagged in the proposal so it
shows a quiet mark on the review page.

**Decisions.**

- **D15. Thresholds.** Pass 2 at ≥ 0.3 with a cap of 60; review page
  unchecked below 0.5 (spec). Recommendation: as stated, tune with T7.
- **D16. Evidence in Phase 3 is quotes only**, from text sources, with the
  locator the model gives (chapter heading and a short anchor phrase) that
  the worker verifies by searching the text; a quote that is not found
  verbatim is dropped. Recommendation: yes. This is the single most
  important hallucination guard and it is cheap.
- **D17. Rejections are remembered.** A proposal the owner left unchecked at
  commit is `rejected`; later scans of the same trope skip that subject.
  Quick-add on the trope page remains the override. Recommendation: skip
  rather than rank last. Showing them again is the "I keep saying no to
  this" annoyance the spec's optional mechanism was meant to prevent.
- **D18. Scoring one trope at a time versus families.** Phase 3 scans one
  trope per job. The sibling-disambiguation idea from the roadmap waits for
  evidence that it is needed. Recommendation: one trope per job.

**Tradeoffs.** Reading the full text in pass 2 for every candidate is the
expensive, slow path, and with this model it costs cents and a minute. If
a pricier model is chosen later, the retrieval experiment in the roadmap
(4.4) is the lever; nothing in T4 precludes it because pass 2 takes "text
to read" as an input and does not care how it was assembled.

**Acceptance.** Scanning Dog Duo proposes the seven seeded instances with
scores, finds at least the SPY x FAMILY and Owl House proposals from the
mock or we learn why not, and produces a verbatim-checked quote for the
Terra Ignota instance from the epub. Checking Pantheon returns the four
seeded tropes as its top matches. A deliberately nonsensical trope
description yields few or no candidates above 0.5.

---

## T5. Review pages

**Scope.** The four owner flows from spec 6.5 to 6.8, built on jobs and
proposals.

**Approach.** Server-rendered pages, no framework:

- `/add/trope`: step 1 is the existing form; "Scan 778 entries" creates a
  job, not a trope. Nothing is saved until commit (spec), so the trope's
  name, description and examples travel in the job payload and the trope
  row is created at commit. Step 2 is the proposal list; step 3 is
  the done line.
- `/add/media`: Phase 3 version. Type a title; if it matches a library
  entry, go straight to "check against all tropes"; if not, the manual
  create form from Phase 2 creates it first. The lookup against external
  sources replaces the first half in Phase 4.
- `/recheck/trope/[slug]` and `/recheck/media/[id]`: create the job on
  first visit, show progress, then the two sections (new instances or
  tropes; new evidence for existing ones).

Each page has three states keyed on the job: running (a progress line
"312 of 778", updated by a 20-line script that polls `GET /api/jobs/:id`
and reloads the page when the status changes), done (the review list), and
failed (the error, a retry link). The review list is one `<form>`: a
checkbox per proposal, a prominence choice as three radio inputs styled as
the text options from the canvas (current one bold), the `who` and text
shown with an "Edit" link that swaps in a textarea via a query parameter
exactly as the trope page does today. "Commit n instances" posts the form
to a `commitProposals` action that creates instances and evidence for the
checked rows, marks the rest rejected, and redirects to the trope or media
page. The count in the button is updated by the same small script; without
JavaScript the button says "Commit selected".

**Decisions.**

- **D19. Minimal JavaScript.** One script for the status poll and the
  button count. Everything else is forms. Recommendation: yes. The two
  review lists are the only places the spec's interaction is dense, and
  radio inputs plus server-side edits cover them.
- **D20. Where draft state lives.** In the job row and its proposals, not in
  browser storage. Reloading the page or coming back later shows the same
  review. Recommendation: yes. A job's proposals are discarded when a new
  scan for the same trope or subject is committed or when the owner presses
  Discard.
- **D21. Progress polling interval.** 2 s while running; stop when done.

**Tradeoffs.** Rendering the prominence picker as radios means three inputs
per row instead of three text buttons; the visual result matches the
canvas and it works without a script. Editing proposal text through a
round trip is slower than an inline textarea toggle but reuses the existing
pattern and keeps the page stateless.

**Acceptance.** Each flow works end to end against a real job; a browser
refresh mid-review changes nothing; the committed instances show up
unverified on the trope and media pages with their quotes in the margin;
Discard leaves nothing behind.

---

## T6. The owner's writing as a source

**Scope.** Your Tumblr posts and annual review posts, fetched per work and
fed into dossiers.

**Approach.** A `media_note` table (`media_id`, `source`, `url`, `text`,
`fetched_at`). The worker, when building a dossier, searches
`beta.midden.net/api/search` for the quoted title restricted to
`blog:wasabipesto` with the API key, keeps hits whose text mentions the
title, and stores them. Annual review posts on wasabipesto.com are fetched
once, split by title mention, and stored the same way. The dossier prompt
includes these as "the owner's own notes", which the writing rules say beat
a rewrite.

**Decisions.**

- **D22. Lazy, cached.** Fetch at dossier-build time, refresh only when
  rebuilding. Recommendation: yes.
- **D23. Relevance.** The noisy-hits problem from the spec is handled by
  asking the dossier prompt to ignore notes that are plainly about
  something else, and by storing hits rather than counts. The media page's
  "n of your posts" line stays a search link (Phase 6 decides more).

**Needs from you.** The midden API key, as `TROPES_MIDDEN_KEY` in the
worker's environment.

**Acceptance.** Pantheon's dossier cites something you wrote about it;
notes for a title that only matches as a common word are not attached.

---

## T7. Calibration line and an eval command

**Scope.** The review page's calibration sentence, and a way to measure a
model or prompt change against the content you have already verified.

**Approach.** The scan result carries, per seed, whether it was found and
its score; the page renders "Found all three of your examples, scoring
0.97, 0.90 and 0.81, plus four others." `tropes-worker eval --trope
dog-duo` (or `--all`) runs pass 1 and 2 for a trope with its *verified*
instances as ground truth, prints recall at 0.5 and at the pass-2 cutoff,
precision among proposals, mean score of true instances, cost and time.
Nothing is written to the site; results go to stdout and a JSON file.

**Decisions.**

- **D24. Include the eval now.** Recommendation: yes. You said you would
  benchmark models; this is the harness, and it is a hundred lines on top
  of T4.

**Acceptance.** The eval runs against the seeded tropes and produces
numbers you can compare across two model ids.

---

## T8. Operations and documentation

**Scope.** Everything needed to run this for real.

- `just api-key <name>` prints a token once and stores its hash.
- `just worker` runs the loop in the foreground; a systemd user unit file
  in `ops/` for ivory; the worker also runs fine under `docker compose
  --profile worker` with `data/sources` mounted.
- Retries: model calls retry on 429 and 5xx with backoff (the client does
  this); jobs do not auto-retry, they fail with the error visible on the
  review page and a "Try again" link.
- Cancel: the review page's Discard sets `cancelled`; the worker checks the
  job status at each progress post and stops.
- Timeouts: per model call 120 s; per job none (progress and the stale
  reclaim cover it).
- Docs: `worker/README.md` grows a section per job kind and the prompt
  files are commented at the top with their input and output contract.
- Tests: Python unit tests for `sources.py` (an epub and a txt fixture),
  the writing check, every output parser; TypeScript tests for the claim
  query, result ingestion and `commitProposals`.

**Decisions.**

- **D25. Where the worker runs.** On ivory next to the site for now, still
  over HTTP. Recommendation: yes; nothing changes when it moves.

---

## 2. Decisions needing your answer

Everything above has a recommendation; these are the ones that change
what gets built.

1. **D11**, model knowledge as a dossier source: yes as recommended, or
   metadata-only until Phase 5?
2. **D17**, rejected proposals: skip in later scans (recommended) or show
   last?
3. **D19**, review pages with one small script and radio inputs
   (recommended) or a richer client-side list?
4. **D24**, build the eval command now (recommended) or later?
5. **T6**, the midden API key, and whether the annual review posts should be
   included.
6. The three nostalgebraist novels: if you download their EPUBs from AO3
   into `braize:tropes-sources`, they join the text set.

Model choice stays as decided (DeepSeek V4.1 Flash via OpenRouter); the
worker needs `OPENROUTER_API_KEY` in its environment before T2 can be
tested against the real model.

---

## 3. What exists for testing today

`data/sources/sources.json` lists 23 text sources on ivory: four epubs you
placed on braize (Empress of Forever, Lent, The Mercy of Gods, Too Like the
Lightning), ten public-domain classics from Gutenberg, Unsong, 17776, The
Egg, qntm's Ra, Fine Structure and Antimemetics (web version), and the three
Crystal books from the author's site. Not fetched: Almost Nowhere,
Floornight and The Northern Caves (AO3 refuses automated fetches), Foreach
(a webcomic, image-based), The Erogamer (adult gate), and the classics still
in copyright.

---

## 4. Order of work and checkpoints

1. T1 and T2 together: a job round-trips with a `ping` kind. Checkpoint:
   you can watch a job move through states on a review page stub.
2. T3: dossiers for everything. Checkpoint: spot-check five dossiers with
   you.
3. T4 with T7: scan Dog Duo and check Pantheon; eval numbers on the seeded
   tropes. Checkpoint: the numbers and the proposals, before any UI polish.
4. T5: the four flows. Checkpoint: you add a trope end to end.
5. T6 and T8: notes, keys, unit, docs.
