# Proposal: seeds that survive typing, and one-field associations

2026-10-28, from the owner's notes after the first four scans with text. Two
flows, one idea underneath: you name the work (and say a word about why) and
the model does the digging; you edit afterwards.

## 1. Seeds for a new trope

Today "Examples" is a textarea, one title a line, matched to the library by
exact title. A colon, a typo or a note in brackets ("The Empire Strikes Back
(Luke)") loses the seed: the scan runs without its calibration and the model's
score for it is never checked.

Proposed:

- **A picker, not a textarea.** The same title field the trope page's Add uses
  (autocomplete over every work and series in the library), one row per
  seed, "Add another example" for the next. Each row has an optional **note**
  field: "Luke", "Merle", "the hand, not the arm". Series count as seeds
  (Friends at the Table: Twilight Mirage).
- **Forgiving matching on submit.** Normalised comparison (case, punctuation,
  diacritics, "and"/"&"), subtitle-insensitive ("Cyberpunk Edgerunners" →
  "Cyberpunk: Edgerunners"), one or two typos tolerated, and a parenthetical
  in the title becomes the note automatically. Before the scan starts, the
  page shows what each seed resolved to — "Cyberpunk Edgerunners → Cyberpunk:
  Edgerunners" — with a link to fix any that went wrong. Nothing runs on a
  seed it cannot place; the page says so instead of a warning after the fact.
- **The note reaches the model.** Seeds are stored as (work, note); the scan's
  examples block becomes "The Empire Strikes Back — Luke" and pass 2 on that
  seed is told which character or element the owner meant, so a score of 0.3
  on a seed means the model disagrees with you, not that it looked at the
  wrong thing.
- Same picker on the trope page's edit view, so seeds can be added or
  corrected later and the next recheck uses them.

Cost: none beyond today's. Work: a `note` column on trope_seed, a seed
resolver with the fuzzy rules (unit-tested against your four scans' seed
lists), the form, the prompt line.

## 2. Adding an association from a title and a note

Today, on a trope page you type a title and press Add; the site creates an
empty association and opens the edit panel for you to write who and text by
hand, then "Find" looks for quotes if you type a prompt. Four steps for one
fact you already know.

Proposed: **one field, one optional note, then it writes itself.**

- On the trope page: a title field (the same picker) and a note ("Luke's
  hand", "the bit with the twins", or nothing). On a work's page the mirror
  form: a trope name and a note.
- Submit creates the association at once — it appears in the list, marked
  "writing…" — and queues one job that does the rest: reads the work's
  dossier and, when the work has its text, the text; writes who and the
  entry in the site's voice, steered by your note; picks up to three verbatim
  quotes (with timestamps, so the frames and the model's look follow as they
  do after a scan); sets prominence. Thirty seconds to a few minutes
  depending on the text's length. The row updates in place when it lands
  (the same polling the Find box uses), unverified and with the edit panel
  one click away, exactly as a scan proposal would be after you accept it.
- Nothing for you to fill in; if the model's text is wrong you edit it; if it
  could not find quotes it says so and the Find box still works.
- Cost: about a cent for a knowledge-only work, a few cents for a long text
  (one full-text call), the same order as one scan proposal.

Work: a `draft_instance` job (the existing `write_instances` prompt plus the
`find_evidence` search, in one go), the two forms, the "writing…" state in
the instance list. The existing manual path stays for the cases where you'd
rather write it yourself.

## Not in this proposal

The screenshot choice (a frame at the quote's exact second often lands on a
cut) — noted for later: grab three frames around the moment and let the look
pick, or prefer the middle of the cue.
