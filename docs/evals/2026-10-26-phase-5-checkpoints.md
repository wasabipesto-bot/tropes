# Phase 5 checkpoints (2026-10-26)

## Checkpoint 1: matching the log to celebrimbor's disk

`tropes-worker media match` over a `find` dump of `/data/{TV,Movies,Anime}`
(62,488 entries, 55,601 files: 37,341 mkv, 12,493 srt, 3,266 avi, 2,051 mp4)
and a copy of Calibre's `metadata.db` (14,928 books), against the library's
pinned identities for the release year. Nothing written.

| type | ok | needs a look | not on the disk |
|---|---|---|---|
| TV series | 156 | 3 | 4 |
| Films | 241 | 3 | 5 |
| Books | 142 | 0 | 12 |

- **Needs a look (6):** two remakes where the pinned year disagrees with the
  folder (*The Fall* 2008 against 2006 and 2022; *What We Do in the Shadows*
  2019 against the 2014 film: the log's entry is the series, filed as a film),
  *Mr. & Mrs. Smith* 2024 against a 2022 folder, *3 Body Problem* against
  `Three-Body Problem`, *Much Ado About Nothing* with three adaptations and no
  pinned year, and *Penny Dreadful* against a folder named `Penny Dreadful X`.
  These go to `/review` with the candidates when the index runs.
- **Not on the disk (21):** five books we already hold as EPUB or text
  (nostalgebraist's three, *Ra*, *Antimemetics*), and sixteen that are simply
  absent (*Tress of the Emerald Sea*, *The Martian*, the Alex Rider and
  Artemis Fowl paperbacks, *Spider-Man: Across the Spider-Verse*, *Night Sky*,
  *Inhumans*, *The Gifted*, *What If...?* and a few Marvel films).
- Of the matched books, 91 have an EPUB and 51 only a MOBI, which the worker
  unpacks itself.

What the disk's naming needed, all now in `media/match.py` with tests:
franchise numbering ("Harry Potter 4 - The Goblet of Fire"), trailing
articles ("Sandman, The"), bracketed release tags ("Food Wars [Shokugeki no
Souma] [2015] [1080p]"), joined names ("Mushishi" for "Mushi-Shi"), a year
inside the log title ("Dune (1984)"), one year of slack between TMDB's date
and the folder's, a near name with the year agreeing ("Scott Pilgrim (2023)"
for *Scott Pilgrim Takes Off*), series-titled Calibre entries ("The Time
Paradox" for *Artemis Fowl and the Time Paradox*) and a shared surname for
co-written books (*Good Omens*).

## Whisper against known-good subtitles (D6)

Arcane S01E01 (43 min), audio streamed from celebrimbor as 24 kbps Opus
(7.4 MB), transcribed on ivory with faster-whisper `small.en`, int8, three
CPU threads, VAD on, greedy decoding:

- **3 minutes** for the episode, about 15× real time on three cores.
- **87 %** of the Netflix subtitle's words appear in order in the transcript
  (a rough 13 % word error rate). Proper names suffer most ("Mouser" became
  "Malzur"); ordinary dialogue is right ("Uh, this weirdo came into the
  shop." / "You think my head is thick?").
- Timing: 401 of 411 reference cues have an overlapping Whisper segment;
  the median start offset is 0.6 s. The 90th percentile is 22 s because the
  voice-activity filter merges quiet stretches into long segments, so a
  frame grabbed from a Whisper timestamp should use the segment's start, not
  its middle.

Usable as the fallback the plan wants: dossiers and scans read it fine, and
quotes from it are marked as transcribed. On celebrimbor's cores `medium.en`
is the better choice (names improve markedly, roughly three times the
time, still minutes per episode).

## Contact sheets at three densities (T11)

Arcane S01E01, keyframes only, tiled by ffmpeg on celebrimbor (52–54 s per
episode on eight threads), read by DeepSeek V4.1 Flash with one call each:

| shots | grid | tile | sheet | tokens in | cost | time |
|---|---|---|---|---|---|---|
| every 80 s (30) | 6×5 | 384 px | 205 KB | 1,103 | $0.0011 | 24 s |
| every 60 s (40) | 8×5 | 320 px | 211 KB | 1,074 | $0.0015 | 7 s |
| every 40 s (60) | 10×6 | 288 px | 277 KB | 1,110 | $0.0009 | 6 s |

Detail did not drop with density: the 40 s sheet named the one-eyed brute,
the goggles pushed up on a forehead, the face markings and tattooed arm, the
glowing green circular device and a "pale, dog-like or pig-like creature";
the 60 s sheet read the title cards. The image is one fixed-size input
whatever the grid, so the cost is flat. Chosen: **every 45 s, a 10×6 grid of
288 px tiles**, one sheet per 45 minutes of running time, so a feature film
gets two or three.
