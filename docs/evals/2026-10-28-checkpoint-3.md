# Checkpoint 3: text-depth dossiers on twenty works, and what the text costs

2026-10-28. Twenty works that now have their text (subtitles from the disk, Calibre
books, the owner's linked EPUBs and transcripts, or only visual notes) had their
dossiers rebuilt at text depth, and five of them were rechecked against every trope
with the text. Before/after dossiers are in `2026-10-28-checkpoint-3/{before,after}/`.

**Cost, honestly:** I quoted "under $0.50" for this checkpoint and it cost $1.39 —
$0.82 for the twenty dossiers (45 calls, 5.0 M prompt tokens, 2.6 minutes),
$0.57 for the five rechecks, $0.005 for the visual-notes probe. Two things I had
wrong: the measured price is about $0.16 per million prompt tokens, 2.3× what I
assumed from the probe, and four of the twenty texts are very long (The Erogamer
856k words, Archer 487k, Almost Nowhere 324k, Marielda 266k) and dominate the
total. The projections below use the measured price.

## The dossiers

| Work | Before (depth/known) | After | Characters | Motifs | Scenes | Arcs | Located % | Words read |
|---|---|---|---|---|---|---|---|---|
| The Erogamer | knowledge/partial | text/strong | 1 → 10 | 4 → 10 | 0 → 10 | 1 → 11 | 0 → 100 | 855,851 (6 blocks) |
| The Amazing Digital Circus | knowledge/strong | knowledge/strong | 8 → 10 | 7 → 8 | 5 → 6 | 4 → 5 | 89 → 100 | visual notes ×8 |
| Station Eleven | knowledge/strong | text/strong | 11 → 11 | 8 → 9 | 6 → 7 | 5 → 6 | 36 → 100 | 34,906 |
| To Be Hero X | knowledge/partial | text/strong | 2 → 13 | 6 → 10 | 2 → 7 | 2 → 6 | 0 → 100 | 52,897 |
| Friends at the Table: Marielda | knowledge/strong | text/strong | 7 → 14 | 6 → 8 | 4 → 7 | 3 → 4 | 0 → 100 | 266,365 |
| Cyberpunk: Edgerunners | knowledge/strong | text/strong | 12 → 13 | 8 → 8 | 7 → 6 | 4 → 5 | 100 → 100 | 45,100 |
| Almost Nowhere | knowledge/partial | text/strong | 2 → 12 | 4 → 10 | 1 → 7 | 1 → 5 | 0 → 100 | 323,597 |
| Delicious in Dungeon | knowledge/strong | text/strong | 11 → 11 | 7 → 7 | 5 → 6 | 4 → 6 | 0 → 100 | 66,049 |
| Mushi-Shi | knowledge/strong | text/strong | 8 → 14 | 7 → 8 | 6 → 9 | 3 → 4 | 22 → 100 | 92,235 |
| Scott Pilgrim Takes Off | knowledge/strong | text/strong | 14 → 14 | 7 → 11 | 4 → 9 | 3 → 6 | 57 → 100 | 17,558 |
| Gideon the Ninth | knowledge/strong | text/strong | 15 → 14 | 8 → 8 | 6 → 7 | 5 → 7 | 45 → 100 | 141,685 |
| Pantheon | knowledge/strong | text/strong | 9 → 14 | 8 → 10 | 7 → 8 | 4 → 4 | 0 → 100 | 70,885 |
| Severance | knowledge/strong | text/strong | 14 → 14 | 10 → 10 | 7 → 7 | 5 → 7 | 100 → 100 | 59,328 |
| Arcane | knowledge/strong | text/strong | 13 → 14 | 8 → 9 | 6 → 7 | 5 → 6 | 100 → 100 | 42,092 |
| Foundation | knowledge/partial | text/strong | 9 → 13 | 6 → 8 | 4 → 7 | 3 → 4 | 43 → 100 | 107,898 |
| Dark | knowledge/strong | text/strong | 13 → 15 | 8 → 11 | 6 → 6 | 3 → 4 | 100 → 100 | 68,719 |
| The Good Place | knowledge/strong | text/strong | 12 → 14 | 9 → 12 | 6 → 6 | 5 → 4 | 100 → 100 | 195,777 |
| Archer | knowledge/strong | text/strong | 11 → 16 | 9 → 17 | 6 → 18 | 4 → 25 | 0 → 100 | 487,418 (3 blocks) |
| The Matrix | knowledge/strong | text/strong | 12 → 12 | 9 → 9 | 8 → 10 | 5 → 3 | 0 → 100 | 8,562 |
| Castlevania | knowledge/strong | text/strong | 12 → 11 | 7 → 8 | 6 → 8 | 4 → 5 | 100 → 100 | 60,707 |

Every dossier now cites real locators (episode labels, chapter numbers). The works
the model only half-knew are where the text matters most: To Be Hero X went from
two characters and generic motifs ("white suits and sunglasses") to thirteen named
characters, the Trust/Fear mechanics, the red stole and the whisper flowers, with
scenes placed by episode; Almost Nowhere from "angels as recurring image" to the
Annes numbered instead of named, the purple blinds, NOWHERE TO HIDE in letters and
blood, the halo above Sylvie. For works the model already knew well (Severance,
Arcane, Dark) the gain is locators and a few more specific scenes, not new
understanding.

The Amazing Digital Circus has no subtitles; its dossier was built from the
eight episodes' visual notes alone, and the motifs changed to what the frames show
(the EXIT door that never leads out, checkerboard floors, red-and-yellow stripes,
the title card's sun and moon). That is plan T11 working as intended.

Long texts went through the season blocks (D7): Archer in three, The Erogamer in
six, merged through the series prompt. One cosmetic defect: merged locators read
"first block, S01E01" — the merge prompt's "which part" wording leaks in. Easy to
fix in the prompt.

## The rechecks

Five works against every trope, with their text (`check_subject`, recheck mode):

| Work | Prompt tokens | Cost | Proposals | Quotes | Notes |
|---|---|---|---|---|---|
| Arcane | 392,844 | $0.058 | 5 | 8 | Arms Outstretched (Vi and Jinx), Time Control, Multiple Timelines (Ekko), all quoted |
| Severance | 116,097 | $0.010 | 3 | 0 | Soul Manipulation 0.75 core; one proposal's quotes were not verbatim and were dropped |
| Castlevania | 434,370 | $0.084 | 5 | 7 | Leash Your Damn Dog (Lenore and Hector) 0.55, the Rebis as Soul Manipulation |
| To Be Hero X | 278,076 | $0.052 | 6 | 5 | We Built Our Own Gods 0.85 core (Zero), Actual Aliens 0.45 |
| Almost Nowhere | 2,276,908 | $0.366 | 20 | 8 | six at 0.90: Numbers for Names, Virtual Worlds, Multiple Timelines, True Reality Warping… |

These are waiting in `/review`. Two observations. First, quotes are now real: every
quote was checked verbatim against the text and the ones the model paraphrased were
dropped with a warning (eight proposals across the five works lost quotes that way).
Second, the cost structure: a recheck sends the whole text once for the check and
once more for *each existing instance* it looks for new evidence on, so Almost
Nowhere's four instances made its 324k-word text a 2.3 M-token job. For long
works, evidence search should read a retrieved slice of the text, not all of it —
that is the retrieval experiment (D8), and these numbers say it is worth doing
before any library-wide rescan.

## Two findings that change the plan

**1. Typesetting bloat.** Nineteen files in two works (Frieren season 2, Food Wars
season 2) carry ASS subtitle tracks whose "dialogue" is 1.1–1.9 million words each:
fansub typesetting — drawing commands (`m -437.5 42.33 b …`) and signs re-rendered
every frame — that pysubs2 leaves in the plain text. Fixed in the parser (drawing
mode and sign styles dropped, per-frame repeats collapsed); the model side now also
refuses any episode text over 60k words. The fix needs a media-worker redeploy and a
re-extraction of those nineteen files. They inflated the library total below.

**2. The library's text is 64.6 million words**, 50.5 M of it television (Bob's
Burgers, It's Always Sunny, Brooklyn Nine-Nine, Blindspot, Letterkenny, Person of
Interest, 30 Rock, Archer each 0.5–1.3 M; the two bloated shows 28 M). At the
measured price a full text-depth rebuild is about **$14**, not the $4 in the plan,
and most of that money goes to long comedies nobody has attached a trope to.

| Rebuild works with text up to | Works | Cost |
|---|---|---|
| 100k words | 341 | $1.79 |
| 150k words | 399 | $3.34 |
| 300k words | 438 | $5.05 |
| 600k words | 462 | $7.24 |
| everything (after the bloat fix, about 36 M words) | 468 | ≈ $8 |

Alternatively, the 113 works that have at least one trope instance: $2.02.

## Recommendation

Rebuild the 399 works up to 150k words now ($3.34): that is every film, every
book, every anime and limited series, and the long shows stay at knowledge depth
until the retrieval experiment makes their scans affordable. Then run D8 on three
long shows before touching library-wide rescans.
