# Phase 4 checkpoint 1: identity resolution (2026-10-24)

`tropes-worker lookup --sample 50` over 43 entries spread across the seven
types plus the known hard cases (Pantheon, Control, Arcane, Castlevania,
Good Omens as book and series, Almost Nowhere, Harry Potter book and film).
No writes. Scores follow `worker/src/tropes_worker/lookup/resolve.py`:
title match 0.5 (exact) or 0.2 (partial), right class 0.3, wrong class −0.6,
unknown class −0.1, creator match 0.25, released after it was logged −0.5,
sitelinks up to 0.1. Confident needs 0.75 and a 0.2 margin over the
runner-up; a Notion Media Link id is confident outright.

## Result

| status | n |
|---|---|
| confident | 36 |
| check | 4 |
| not_found | 3 |

| type | confident | check | not found |
|---|---|---|---|
| Album | 4 | 1 | 0 |
| Book | 7 | 0 | 1 |
| Game | 6 | 0 | 0 |
| Movie | 6 | 0 | 0 |
| Other | 2 | 0 | 2 |
| Podcast | 2 | 3 | 0 |
| TV Series | 9 | 0 | 0 |

Every confident match was checked against its Wikidata description and is
right (93 %). The four "check" results are real ambiguities: *The Beautiful
Game* (two albums of that name, neither by Vulfpeck, which Wikidata lacks),
and three podcast seasons (*Friends at the Table: Marielda* and *Partizan*,
*The Adventure Zone: Balance*) matched to their parent show, offered as a
check because the granularity differs. The three not found are works
Wikidata does not have: *Almost Nowhere* and *The Erogamer* (web fiction)
and *Foreach* (a webcomic; the only hit was an npm package, rejected as an
unknown kind). None of the 43 is a wrong confident match.

Time: 1.3 s per entry with six workers on a cold cache (56 s for the sample,
161 requests); 0.4 s per entry warm.

## What the sample changed

The first run had 30 confident, 8 check, 5 not found. Fixes made on it:

- **Class-restricted search.** Plain Wikidata search for "Pantheon" returns
  the Paris mausoleum and never the series; a full-text search with
  `haswbstatement:P31=…` over the type's class family finds it first. Colons
  and quotes are stripped from the query (they are CirrusSearch syntax:
  "Cyberpunk: Edgerunners" returned nothing with the colon).
- **Editions fold into their work.** Books came back as ties between the
  novel and its Bloomsbury paperback; an edition (P31 version/edition,
  P629 edition of) now merges into its work and donates its Goodreads id.
  Good Omens' Notion link pointed at a 2006 edition and now pins the 1990 novel.
- **Parent-title retry.** "Friends at the Table: Marielda" has no item of its
  own; the part before the colon is tried and offered as a check.
- **mul labels.** Wikidata stores brand-like labels under the `mul`
  language; `Control Resonant` and `Remedy Entertainment` had empty English
  labels and scored as "title differs". Labels are now read with
  `languages=en|mul`.
- **Per-site hits link back.** When Wikidata search fails but Steam, TMDB,
  Open Library, MusicBrainz or iTunes finds the title, the hit's id is looked
  up as a Wikidata statement; a match is confident (Control Resonant resolved
  to Q116947317 this way).
- Margin 0.25 → 0.2 (a creator match alone should decide), unknown kinds
  −0.1 (so an npm package does not reach "check").

## The first backfill batch

Job 35, 200 entries chosen in id order, run for real with posters and
genres: 170 confident, 23 check, 7 not found; 1945 requests (182 from the
cache); 621 s; $0.024 of model calls (tiebreaks and genre mapping). The
checks are mostly small-label albums the model correctly refused to match
("none of the listed albums is by Mother Falcon") where the MusicBrainz
search then offered a candidate, and web serials (the Crystal trilogy,
Floornight) with nothing to find. The owner reviews each batch on
`/metadata`.
