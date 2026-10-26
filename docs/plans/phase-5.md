# Phase 5 plan: local media and evidence

Written 2026-10-26 for approval before any of it is built. Same shape as
`phase-3.md` and `phase-4.md`: tasks, each with scope, approach, decisions
with a recommendation, implementation detail and tradeoffs. The bias is the
same: the fewest moving parts. No new services; the worker gains three job
kinds and reads your media where it already lives, and the site gains one
upload endpoint, one file route and three columns.

What Phase 5 delivers (roadmap): every logged work that exists as a file on
celebrimbor gets its text (subtitles, EPUB, transcript) indexed; dossiers
are rebuilt from the text for those works; pass 2 reads the real text; and
evidence becomes real: quotes with chapter or timestamp locators, frames at
the timestamp, clips on request. Section 1 lists what was measured today so
the recommendations rest on numbers.

---

## 0. Shape of the system after Phase 5

```
site (Astro, SQLite)                      worker (Python, ivory)                 celebrimbor (your homelab)
  local_source rows per file         <──  index_local: match log → files,   ──>  /data read-only over sshfs
  evidence files under data/evidence      pick a text source, extract text  ──>  ffmpeg/ffprobe run there over ssh,
  POST /api/evidence (frames, clips)      extract_evidence: frame or clip        only the output comes back
  /evidence/… served with caps            at a timestamp, upload
```

Unchanged: the worker never opens the database; nothing is saved until the
owner commits, except on the automatic path; the model reads text, never
pixels. New: nothing from `/data` is ever copied to ivory except extracted
text and the evidence files themselves.

---

## 1. What was measured (2026-10-26)

**celebrimbor** (Tailscale 100.104.85.19). SSH as `justin` works from ivory
under the tailnet's SSH policy (`claude` is refused). `/data` is a 55 TB
array with 828 GB free, laid out as Plex expects:

| Folder | Entries | Layout |
|---|---|---|
| `Movies` | 2,830 | `Title (Year)/file.mkv`, often an `.srt` beside it |
| `TV` | 908 | `Title (Year)/Season 01/Show.S01E01.Episode.Name.….mkv` |
| `Anime` | 99 | same as TV |
| `Books` | 6,019 | a Calibre library (`metadata.db`, 14,928 books: 12,596 MOBI, 3,052 EPUB; identifiers: ISBN 10,622, Amazon ASIN 8,687, Google 2,185, Goodreads 68) |

Of 4,000 sampled video files: 2,517 mkv, 351 avi, 47 m4v, 14 mp4; 12,494
external `.srt`/`.ass` files across the three video folders; embedded
subtitle streams are common (Arcane S01E01 carries English, English SDH and
six other languages as subrip). ffmpeg 7, ffprobe, mediainfo and python3 are
installed there; no Calibre command line, no GPU; 48 cores at load 2–3.

**Coverage of your log**, matching folder names to titles the way the
Phase 4 resolver normalises them: TV 155 of 163, films 198 of 249, books 125
of 154. The misses are naming, not absence: "Star Wars: A New Hope" against
a folder named by episode, the Lord of the Rings and Marvel titles, the
Harry Potter books under their US titles, "The Final Empire" under
Mistborn. Phase 4's pinned identities carry the release year and the IMDb,
Goodreads and ISBN ids, which closes most of that gap (T2).

**Throughput.** ivory to celebrimbor is 116 ms away at about 10 MB/s over
ssh and 2 MB/s over sshfs, so reading one 1.9 GB episode across the link
takes three to fifteen minutes. Run on celebrimbor itself and streamed back,
the same episode's subtitles take 8 s, a frame at a timestamp 1.9 s, and a
10 s 640 px clip 4.2 s. That decides T1.

**ivory**: 4 cores, 7 GB, 11 GB free. Whisper on it is out; it can hold
extracted text (about 50 KB per episode, under 200 MB for everything) and
evidence files (25 KB per frame, 0.5–1.5 MB per clip).

**Your three sources.** nostalgebraist.net serves EPUBs of Almost Nowhere,
The Northern Caves, Floornight and The Apocalypse of Herschel Schoen; its
robots.txt defines the content-signal vocabulary but sets no signal, which
by its own text "neither grants nor restricts". Transcripts at the Table is
a Google Site whose season pages link one published Google Doc per episode;
`docs.google.com/document/d/<id>/export?format=txt` returns the transcript
(Marielda 01: 129 KB, speaker-labelled, with timestamps in the header).
OpenSubtitles has a REST API behind a free API key: 5 downloads a day
without an account, 20 with a free account, 1,000 for VIP ([forum][os1],
[guide][os2], [help centre][os3]).

[os1]: http://forum.opensubtitles.com/t/vip-active-on-website-but-api-still-limited-to-5-downloads-day/7934
[os2]: https://apidog.com/blog/opensubtitles-api/
[os3]: https://opensubtitles.tawk.help/article/about-the-api

**What exists already.** 23 text sources (EPUB and txt) under
`data/sources`, `sources.py` turning them into chapter-marked text with
verbatim quote checking, dossiers at `text` depth for those 23, pass 2 and
`new_evidence` reading whole texts, and an `evidence` table with
`kind quote|frame|clip`, `file_path`, `width`, `height`, `duration_ms` and
`public` waiting for files.

---

## 2. Tasks

| # | Task | Size | Depends on |
|---|---|---|---|
| T1 | Media access: the read-only mount and running ffmpeg on celebrimbor | S | |
| T2 | `index_local`: match the log to files, record what each work has | M | T1, Phase 4 identities |
| T3 | Text from video: subtitles, with timestamps | M | T2 |
| T4 | Text from books and transcripts: Calibre, nostalgebraist, FaTT | S | T2 |
| T5 | Text-depth dossiers and pass 2 on real text; long works | S | T3, T4 |
| T6 | Evidence extraction: timestamped quotes, frames, clips | M | T3 |
| T7 | Evidence on the site: upload, files, serving, the caps | S | T6 |
| T8 | Rechecks propose new evidence for video works | S | T6 |
| T9 | Games and podcasts without text | ? | |
| T10 | Operations: config, tests, docs, costs | S | all |

---

## T1. Media access

**Scope.** The worker can list your media, read small files, and get
subtitles, frames and clips out of video, without moving video.

**Approach.** Two paths, both read-only:

1. `sshfs -o ro justin@celebrimbor:/data /home/claude/celebrimbor` on ivory
   (mounted today for the measurements; `just mount-media` keeps it), used
   for directory listings, `.srt`/`.ass` files, EPUB and MOBI files, Calibre's
   `metadata.db` and `.opf` files. All small.
2. ffmpeg and ffprobe run on celebrimbor over ssh, with only their output
   streamed back: `ssh justin@celebrimbor ffmpeg -i <file> -map 0:s:0 -f srt -`
   for subtitles, `-ss <t> -frames:v 1 -f image2 -` for a frame, a short
   `-t` window encoded to fragmented mp4 on stdout for a clip. Nothing is
   written on celebrimbor.

Configuration: `TROPES_MEDIA_ROOT` (the mount, or a local path once the
worker lives in the homelab) and `TROPES_MEDIA_SSH` (the host to run ffmpeg
on; empty means locally). The code path is the same either way: a
`MediaRunner` with `list`, `read`, `probe`, `subtitles`, `frame`, `clip`.

**Decisions.**

- **D1. ffmpeg on celebrimbor, over ssh, as `justin`.** The mount alone is
  fifty times too slow for video. Recommendation: yes; the commands are
  reads with output on stdout, and the mount is `ro`. If you would rather
  not have the worker run anything on celebrimbor, the alternative is
  copying each file across the link before extraction (hours per show,
  and space ivory does not have).
- **D2. Mount lifetime.** A `just mount-media` recipe and a line in the
  worker's start-up that checks the mount is live, rather than fstab, so a
  dead link fails loudly in the job instead of hanging the box.

**Acceptance.** `tropes-worker media probe "TV/Arcane (2021)/Season 01"`
lists the episodes with their subtitle streams in under five seconds.

---

## T2. `index_local`

**Scope.** For every logged work, find its files and record them, so every
later step reads `local_source` rows instead of guessing paths.

**Approach.**

- **Video.** Match a log entry to a `Movies`, `TV` or `Anime` folder by
  normalised title (the Phase 4 `norm`) plus year: the folder's `(Year)`
  against `details.start` from the pinned identity. Films need the year to
  agree when both are known (remakes); series match on title and the
  nearest year. Episode files are parsed for `S01E03` and ordered; season
  folders give the fallback. Each file becomes a `local_source` row with
  `kind video`, the path relative to the media root, `label` (`S01E03`),
  and `meta` (duration, subtitle streams with language and SDH flag, an
  external `.srt` if present).
- **Books.** Calibre's `metadata.db` (read through the mount) matched by
  ISBN or Goodreads id from the pinned identity first, then title plus
  author. The EPUB is preferred; MOBI-only books (most of the library) are
  unpacked on the worker with the `mobi` package (KindleUnpack; tested
  importable). One `local_source` row, `kind text`.
- **Ambiguity.** Several folders matching one entry, or a year disagreement
  on a title match, goes to `/review` as "Local files to check" with the
  candidates and "Not this file"; a confident match is recorded without
  asking. The media page's "Local copy" line shows what was matched (the
  folder, the episode count) with an owner-only "Not these files".
- **When it runs.** Once over the library (`just index-media`), on the
  automatic path after a new entry's lookup, and `just index-media --ids`
  for a few.

**Decisions.**

- **D3. Automatic matching with the year check.** Recommendation: yes;
  title plus year against a Plex-style layout is precise, and the review
  list catches the rest. The alternative, confirming 480 matches by hand,
  is the Phase 4 backfill again for less reason.
- **D4. Schema: three columns on `local_source`** (`label`, `meta` JSON,
  `indexed_at`), not a new table. Phase 3 left the table for exactly this.

**Acceptance.** The match report (checkpoint 1): matched, ambiguous and
unmatched counts by type, with the unmatched titles listed.

---

## T3. Text from video

**Scope.** Subtitles for every matched film and episode, as text the
matcher can read and quote with timestamps.

**Approach.** Source order per file: an English `.srt`/`.ass` beside the
file; an embedded English subrip or ASS stream (plain over SDH, SDH over
nothing); OpenSubtitles by IMDb id and episode (D5); otherwise none, listed
for D6. Cues are parsed with `pysubs2`, cleaned (tags, sound descriptions in
brackets, music notes, duplicate lines from SDH) and written as one line
per cue, `[12:40] line`, under a `## S01E03 Episode Title` heading per
episode; a series becomes one text in episode order, a film one text.
Cached like the EPUB texts are today, keyed on file path and size. Text per
45-minute episode is about 8k tokens with the timestamps (6k without);
Arcane's two seasons are about 150k, a long sitcom is over a million (D7).

**Decisions.**

- **D5. OpenSubtitles as the third source.** Needs a free account and its
  API key as `TROPES_OPENSUBTITLES_KEY` (20 downloads a day). Recommendation:
  yes, as a fallback only; with 12,494 external files and embedded streams
  on most releases, the expected volume is small. Without it, the files
  with no subtitles simply have no text.
- **D6. Whisper for what is left.** Options: faster-whisper on
  celebrimbor's 48 cores (software to install there, roughly real time per
  file), on demoux's GPU when you lend it, or not at all. Recommendation:
  decide after checkpoint 2 says how many files lack subtitles; my guess is
  under ten.
- **D7. Long works.** The model's window is a million tokens. A series text
  over about 600k tokens is read in season blocks: the dossier is built per
  block and merged (the series-dossier path exists), and pass 2 reads the
  block the dossier's locators point at plus the one around it, rather than
  everything. Recommendation: this; it costs one more call for perhaps a
  dozen long shows and keeps the rest unchanged.

**Acceptance.** Checkpoint 2: text coverage by type, five shows' texts
read by eye for cue cleanliness, and the list of files with no subtitles.

---

## T4. Text from books and transcripts

- **Calibre.** EPUB through the existing path; MOBI unpacked to HTML then
  through the same cleaner. ISBN and Goodreads ids make the match exact.
- **nostalgebraist.net.** Four EPUBs, fetched once into `data/sources` the
  way a reader would (one request each, your own download). The site sets
  no content signal; if you would rather download them yourself and drop
  them in the folder, nothing changes.
- **Friends at the Table.** One transcript per episode from the published
  Google Docs (`export?format=txt`), one text per season with
  `## Episode` headings and the speaker labels kept; the Divine Cycle
  series gets the seasons concatenated. Marielda, Counterweight, Twilight
  Mirage, Partizan and Palisade are in your log; the site has them all.
  Fetched politely, once, and cached. Locators are episode and timestamp
  where the transcript carries one, else episode.
- **Other podcasts** (Cortex, Hello Internet, The Adventure Zone): no
  transcripts of this kind that I know of; see T9.

**Acceptance.** Checkpoint 2 includes book coverage; Gideon the Ninth and
Oathbringer come from Calibre (both are EPUB there).

---

## T5. Dossiers and pass 2 on real text

**Scope.** What Phase 3 already does for 23 works, for everything with
text.

**Approach.** Nothing new in the prompts: `dossier_needed` already
rebuilds a work at `text` depth when a source appears, and pass 2 and the
check already take the whole text. Series texts get the D7 blocks. The
dossier prompt's locator instruction ("name the chapter heading as it
appears") already yields `S01E03`-style locators once episodes are headings.

**Cost.** Text-depth dossiers for everything matched: roughly TV 155 × 60k,
films 198 × 15k, books 125 × 120k ≈ 27M input tokens ≈ **$4**, one call
each. After that a trope scan reads full text for its candidates: up to 60
works × 100k ≈ 6M tokens ≈ **$1 per scan**, against $0.30–0.50 today. Both
are over the $0.50 line, so the rebuild is one approval and scans are
priced on the review page.

**Decisions.**

- **D8. The retrieval experiment** (roadmap 4.4) is checkpoint 3's
  question, measured, not assumed: one trope rescanned with full text
  against the same scan with the dossier plus the top chunks by similarity.
  If retrieval finds the same evidence for a fifth of the tokens, pass 2
  uses it for long works. Recommendation: run the experiment on the 20-work
  sample before the full rebuild; it decides whether scans cost $1 or 25 c.

**Acceptance.** Checkpoint 3: on 20 works, text dossiers read beside the
knowledge ones; one rescan of Leash Your Damn Dog with text, its cost, and
the retrieval comparison.

---

## T6. Evidence extraction

**Scope.** Quotes with real locators, and a picture or clip at the moment
of a video quote.

**Approach.**

- **Quotes.** Pass 2 and the check already return quotes and verify them
  verbatim; with timestamped text the verification also yields the cue, so
  the locator becomes `S01E03 12:40` (or `12:40` for a film, `ch. 7` for a
  book) and the proposal's evidence item gains `at` (seconds) and `end`.
  Quotes are trimmed to 100 words at the source (spec caps).
- **Frames.** For each committed video quote, one frame at the cue's
  midpoint: ffmpeg on celebrimbor, scaled to 640 px wide, WebP, uploaded to
  `POST /api/evidence/<id>/file`. The evidence row gets `file_path`, width
  and height. The spec's 16:9 placeholder is what the margin already
  renders.
- **Clips.** Up to 30 s around a quote (or a model-given range), 640 px
  H.264 with audio, fragmented mp4, same upload. Clips are large and rarely
  needed, so they are deliberate (D10).
- **Caps.** Ten frames per work per trope and 30 s per clip are enforced at
  extraction; the `public` flag stays for Phase 6.

**Decisions.**

- **D9. Extract at commit, not during the scan.** A scan proposes dozens of
  quotes you then discard; grabbing a frame for each would cost time and
  files for nothing. Recommendation: `commitProposals` queues one
  `extract_evidence` job for the accepted instances whose locators carry a
  timestamp; the review page shows the quote with its timestamp and the
  frame appears on the page when the job lands (minutes).
- **D10. Clips on request.** A "Clip" button beside a timestamped quote in
  the instance edit panel queues the extraction for that one quote.
  Recommendation: this, rather than a clip for every quote; frames are
  what the margin needs, clips are for the handful you want to show.

**Acceptance.** The roadmap's line: a Gideon the Ninth quote with a chapter
locator and a Pantheon frame with an episode timestamp appear on the live
pages from the pipeline, not by hand.

---

## T7. Evidence on the site

- `POST /api/evidence/<id>/file` (worker bearer; multipart; WebP or mp4;
  size and type checked, like the poster upload), writing
  `data/evidence/<instance>/<evidence id>.webp|.mp4`.
- `/evidence/[...path]` serves the files with a long cache header (the
  Phase 4 poster route pattern). Phase 6 adds the `public` check.
- The media page's "Local copy" line (T2), the frame and clip rendering the
  margin already has (the clip gets a `<video controls preload="none">`),
  and the "Clip" button (D10).
- Backups: `just backup` already tars `data/evidence`; posters and text
  caches stay out, as rebuildable.

---

## T8. Rechecks propose new evidence for video

`new_evidence` already runs on rechecks for instances whose work has a
text; with subtitle texts that now includes TV and films, and the proposals
carry timestamps. No new UI: the "New evidence for existing instances"
section is already there, and committing queues T6.

---

## T9. Games and podcasts without text

You said games have no good source yet. What exists: fan-wiki transcripts
for a few games (manual, per game), YouTube longplays' auto-captions (low
quality, gray), the model's own knowledge (strong for most big releases),
and your own notes. Podcasts other than FaTT: The Adventure Zone has fan
transcripts in places I have not checked; Cortex and Hello Internet have
none I know of. Recommendation: leave games and those podcasts at knowledge
depth in this phase, keep the per-work "paste a text file" path
(`just link-sources`), and revisit when a particular work needs evidence.
Albums stay without text.

---

## T10. Operations, tests, docs

- Config: `TROPES_MEDIA_ROOT`, `TROPES_MEDIA_SSH`, `TROPES_OPENSUBTITLES_KEY`
  (optional), `TROPES_TEXT_CAP_TOKENS` (D7). `just mount-media`,
  `just index-media [--ids]`.
- Tests: the folder matcher against a table of hand-checked names
  (episode-numbered Star Wars, LOTR, remakes); SRT and ASS cleaning against
  saved cue files; MOBI unpacking against a small fixture; the FaTT doc
  parser; locator derivation from cues; the upload endpoint; the caps.
- Docs: `worker/README.md` gains the media section; `ROADMAP.md` Phase 5
  status at the end.

---

## 3. Decisions needing your answer

1. **D1.** The worker runs ffmpeg and ffprobe on celebrimbor over ssh as
   `justin`, read-only by construction. Yes, or copy files across instead.
2. **D5.** An OpenSubtitles account and API key for the fallback.
3. **D6.** Whisper, decided after checkpoint 2: on celebrimbor (something
   to install there), on demoux, or not.
4. **D7.** Long shows read in season blocks over 600k tokens.
5. **D8.** The retrieval experiment before the full rebuild.
6. **D9, D10.** Frames at commit; clips on request.
7. **T9.** Games and the non-FaTT podcasts stay at knowledge depth for now.
8. **Costs.** About $4 for the text-depth rebuild (one approval when the
   time comes) and about $1 per trope scan after it, unless D8 brings it
   down. The index, subtitle and extraction work costs nothing in model
   calls.
9. **nostalgebraist's EPUBs:** the worker fetches them once, or you drop
   them in `data/sources`.

---

## 4. Order of work and checkpoints

1. T1, T2 over the whole log. **Checkpoint 1:** the match report; nothing
   extracted yet.
2. T3, T4. **Checkpoint 2:** text coverage by type, five shows' texts read by
   eye, the list without subtitles (decides D6).
3. T5 on 20 works plus the retrieval experiment. **Checkpoint 3:** dossier
   quality, one rescan with text and its cost, go/no-go on retrieval.
4. T6, T7, T8. **Checkpoint 4:** the Gideon quote and the Pantheon frame on
   the live pages.
5. The full text-depth rebuild (approval), T10.
