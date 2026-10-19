# Trope Log: design and product spec

This is the handoff brief for Trope Log, a personal TVTropes-style site built on Wasabi's media log. It goes with the Claude Design canvas "Trope Log" and records the decisions made while designing it, most of which are not visible in the artboards themselves. Where this document and the canvas disagree, this document wins; the canvas is a mockup with hardcoded data.

Tech stack, hosting, and whether the site is fully public or only open source are still undecided. Nothing below assumes a particular stack.

---

## 1. What the site is

A catalogue of tropes Wasabi notices across everything they have read, watched, played and listened to. Each trope has a page describing it and listing every work in the log where it appears, with a short explanation and evidence pulled from the source material. Each media item has a page listing its tropes, ratings, links and poster.

The defining feature is that associations are found by an LLM. Adding a trope scans the whole log for instances. Adding a media item checks it against every trope. Results go live immediately; Wasabi verifies, adjusts or removes them at leisure.

It is a resource for one person. If it is published, the public sees the same content minus the editing controls. Unverified instances are shown publicly alongside verified ones; that is a deliberate choice, not an oversight.

---

## 2. Principles

These came out of four rounds of review and should guide anything not covered below.

**Every element earns its place.** Add a component only if it communicates something useful or enables something. Remove anything decorative or redundant. If the same information appears twice on a screen, one of them goes.

**Clear and dense.** Plain text with minimal formatting. No cards, chips, pills, padded boxes, coloured badges, or big buttons. But if a user has to ask what something is or does, it needs to be clearer, not hidden.

**Prominence is the main axis; verification is a whisper.** Instances are organised by how central the trope is to the work. Whether Wasabi has checked an instance is shown with a small mark and nothing more.

**Auto and verified live together.** There is no review queue, no drafts, no staging area. A model-found instance is a real instance from the moment it is committed.

**Wasabi makes the judgment calls.** The model proposes additions. Only Wasabi changes prominence, removes associations, or edits text. Rechecks never remove or downgrade anything.

**Built for scale.** Expect dozens of tropes and nearly 800 media items. Any list that could grow must not overflow: no long chip rows, no sidebars listing every trope, no "related" lists that grow without bound.

**The text describes the work.** See section 9. Copy on the site reads as if a person wrote a reference entry, not as notes from a model to its user.

---

## 3. Visual system

### Type

One family: **Source Serif 4** (Google Fonts, optical sizes 8–60, weights 400/600/700, italic 400). Georgia as fallback. Body 18px, line-height 1.6. Secondary text 15–16px.

- Page title (h1): 44–48px, weight 700, line-height 1.1.
- Prominence group labels: 19px, weight 700, all small caps (`font-variant-caps: all-small-caps; letter-spacing: .06em`).
- Instance title (media or trope name): body size, weight 700.
- Character/pair lead-in on an instance: italic, followed by a period.
- Numbers in tables and ratings: `font-variant-numeric: tabular-nums`.

### Colour

Near-white ground, near-black text, one link blue. Nothing else carries meaning through colour except the rating bars.

| Token | Value | Use |
|---|---|---|
| ground | `#FCFCFA` | page background |
| ink | `#1B1B1B` | body text, headings, rules under group labels |
| quiet | `#66645E` | secondary text, metadata, footer (passes 4.5:1 on ground) |
| link | `#1F4FA3`, hover `#0E2F6B` | links and text buttons |
| rule | `#E4E3DF` | light dividers between instances, header/footer borders |
| rule-faint | `#ECEBE7` | table row dividers, spoiler bar |
| field border | `#C9C7C0` | inputs, underline-style inputs |
| danger | `#9A2B1E` | "Remove" text button only |
| placeholder | `#E7E6E1` | evidence thumbnails before an image loads |

### Links

All links are underlined (1px, offset 3px). Media and trope names that link are underlined **in the text colour** (`#1B1B1B`), not blue, so headings stay calm. Ordinary links in prose are blue.

### Controls

- **Text buttons** look like links (blue, underlined). Used for nearly every action: Edit, Save, Cancel, Show all, prominence choices.
- **Primary button** (one per flow, for the committing action only): solid ink background, ground-coloured text, 3px radius, 44px tall. Examples: "Scan 778 entries", "Commit 6 instances", "Add to library", "Add 4 selected".
- **Inputs**: either underline-only (search, filters, quick-add) or a plain 1px bordered box (multi-line fields in forms).
- **Checkboxes**: native, `accent-color: #1B1B1B`.
- Touch targets stay at least 44px tall through padding even when the visible element is text.

### Page frame

- Header: site name "Trope Log" (bold, links to Tropes), then text nav (Tropes, Library, Add trope, Add media), then an underline-style search field pushed right. Thin rule below.
- Footer: thin rule above, quiet 15px text: "Trope Log", links to Tropes and Library, and `wasabipesto.com` pushed right. Present on every page.
- Content width: 1440px max for trope, media and library pages (they use the wide layout below); 980px for index and form pages.

### The margin layout (trope and media pages)

Chosen in review as the layout to keep. It makes use of a wide monitor and keeps evidence next to the text it supports.

Three-column grid per row: `150px | minmax(0, 660px) | minmax(0, 1fr)`, column gap 48px.

- **Left column**: prominence group label, shown only on the first instance of each group, with a 2px ink rule above and the group count right-aligned in quiet text. On media pages the header row puts the poster here.
- **Middle column**: the instance itself. Capped at 660px so prose stays readable.
- **Right column (margin)**: evidence. Takes all remaining width. Quotes wrap freely; frames and clips form a grid (`repeat(auto-fill, minmax(150px, 1fr))`, max 640px wide).

Each instance row starts with a 1px rule across the middle and margin columns. First row of a group gets 48px top spacing, later rows 20px.

Below 1100px viewport width the grid collapses to one column: group label, then text, then evidence, with the margin's top rule removed. Spacing on narrow screens was noted as needing more work.

---

## 4. Components

### Rating mark

The average rating as a number, followed by five small vertical bars, one per axis, always in this order: **Medium, Story, Tone, Enjoyability, Effect**. The bars sit to the **right** of the number everywhere they appear.

- Bar height is proportional to the score out of 5 (library: max 18px, 4px wide, 2px gap; media page: max 26px, 6px wide, 3px gap).
- Bar shade: `#1B1B1B` for 4.5 and above, `#7A786F` for 3 to 4.4, `#BDBAB1` below 3. A missing axis is a 2px stub in `#E4E3DF`.
- The full breakdown ("Medium 5, Story 4, Tone 4, Enjoyability 4.5, Effect 5") is in the hover title and the accessible label. It is **not** written out on the page.
- The average is the mean of whichever axes are filled in. Albums usually only have Medium. This may not match the Notion "Average Rating" formula, which was not inspected; check it and match it.

### Verification mark

A 16px stroke icon before the instance title. Verified: a small check. Unverified: a dashed circle. Both in quiet grey, darkening on hover. Clicking toggles verification. Hit area padded to 44px via negative margins so it doesn't push the layout. Nothing else marks verification state. On public pages the mark is not shown at all.

### Spoilers

Inline, TVTropes-style. Authors wrap text in `||double bars||`.

- Hidden: the text is transparent on a faint `#ECEBE7` bar, no padding, `box-decoration-break: clone` so it wraps across lines cleanly.
- Click reveals **in place**. Nothing shifts, because the same inline element stays rendered and only its colour changes. (An earlier version swapped a button for a span and the layout jumped; don't do that.)
- Revealed text keeps a faint dotted underline so the boundary is still visible. Clicking again hides it.
- No "show all spoilers" toggle. No help text about the syntax on the page.
- Accessible: the element is focusable and announces itself as a spoiler.

### Evidence

Evidence is not decoration; it is shown inline in the margin column for every instance that has it.

- **Quote**: italic, slightly darker than body (`#3A3A36`), followed by a quiet citation (chapter, page, or EPUB location). Quotes can be a paragraph long.
- **Frame**: 16:9 still with a caption like `S01E03 12:40`.
- **Clip**: same as a frame with a play glyph; caption gives the range, like `S01E05 3:10–3:42`.

All evidence comes from Wasabi's local copies. The canvas shows placeholders for all of it.

### Trope links

Trope descriptions (and media descriptions) can link other tropes with `[[Trope name]]`. This replaces any "related tropes" list. Example from the Dog Duo description: "When the bond stops being figurative it usually becomes [[Soul Manipulation]] or [[Hive Mind and Unification]]." The edit field says "[[Trope name]] links to another trope" under it; that is the only help text that stays.

### Prominence

Three levels, in this order everywhere:

- **Core theme**: the association drives the work.
- **Recurring**: a major thread, not the spine.
- **Brief**: a scene, an arc, a nod.

Brief items are never collapsed or hidden; they are already at the bottom.

---

## 5. Data model

Field names are suggestions.

**MediaItem**
- `title`, `type` (Book, TV Series, Movie, Game, Podcast, Album, Other; displayed as "TV" for TV Series), `creator`
- `logged_date` (full date; displayed as year in tables)
- `ratings`: `medium`, `story`, `tone`, `enjoyability`, `effect`, each 0–5 in 0.5 steps, nullable (sourced from Notion, see 8.1)
- `description` (markdown-ish, supports `[[trope links]]` and `||spoilers||`)
- `poster` (optional image; seeded from Notion's Image Link)
- `links`: list of `{site, url, score?}` (Wikipedia, IMDb, TVDB, TMDB, MyAnimeList, AniDB, Anime News Network, Goodreads, Steam, Letterboxd, Metacritic, Rotten Tomatoes, official site, etc.)
- `metadata`: seasons/episodes, air dates, studio/network, genres, source
- `local_source`: path to the local copy, plus what has been indexed (subtitles, EPUB text, sampled frames)
- `series` grouping (optional): several log entries can belong to one work for trope purposes. Terra Ignota is four separate log entries; the Dog Duo instance attaches to the series.

**Trope**
- `name`
- `description` (this is also the prompt the matcher reads; supports `[[links]]`)
- `seed_examples`: list of media titles given when the trope was created, used for calibration
- `notable`: ordered list of instance ids pinned as notable

**Instance** (trope ↔ media association)
- `trope_id`, `media_id`
- `who`: the character, pair or element (for example "Viv and Zanj", "MIST", "The UIs as a class")
- `text`: the explanation (supports `||spoilers||`)
- `prominence`: core | recurring | brief
- `verified`: boolean
- `score`: the model's calibration score at the time it was found (0–1). Shown in add and recheck flows only; not shown on trope or media pages.
- `origin`: model | manual (stored, never displayed)
- `evidence`: list of Evidence

**Evidence**
- `kind`: quote | frame | clip
- `locator`: chapter/page/EPUB CFI for text; episode + timestamp or range for video
- `content`: quote text, or the extracted image or clip file
- `verified` is not needed per evidence item

**Rejected suggestion** (optional): if a rejection mechanism is wanted later. In the current design, removing an instance is simply removal; there was an earlier idea to remember rejections so they aren't proposed again, which fits naturally into the recheck flow if needed.

---

## 6. Pages

### 6.1 Tropes index (`Tropes`)

A single flat, sortable, filterable table of every trope. No groupings, no collections, no drafts section.

- Columns: Trope (link), Instances (count, right-aligned), Examples (first three titles, then "+n").
- Sort by name or by count; filter by trope name or example title.
- Header shows "n of 27".

Collections (like grouping the eleven Mind/Machine/Divine/Animal tropes) were tried and removed; nobody could say what they were for. Revisit only if a real need shows up.

### 6.2 Trope page (`Main`, e.g. Dog Duo)

Margin layout.

- Title.
- Description paragraph, with `[[links]]` rendered as links.
- Under it, quiet: "Edit description" and "Recheck instances". Editing shows a textarea in place with Save and Cancel. **Saving does not trigger a rescan.** Rechecking is a separate, explicit action.
- "Notable:" followed by the pinned instances as links.
- Instances grouped by prominence (Core theme, Recurring, Brief), group label in the left column.
- Each instance: verification mark, media title (underlined link), quiet type label ("book", "TV", "web serial"), "Edit" at the right; then the italic `who` and the text; evidence in the margin.
- Inline "Edit" opens a panel under the text: Prominence (three text options, current one bold), Edit text, Add evidence, Pin as notable, Remove (in red). "Done" closes it.
- After the list: a 1px ink rule, then "Add media to this trope" with an autocompleting title field and an Add link. This is how manual associations are made.
- Removed during review, do not bring back: the "7 instances, 2 unverified" count line, the type filter (All/Books/TV/Games), the show-all-spoilers toggle, the "matching prompt" details block, the related-tropes line, any help text about spoiler syntax.

### 6.3 Media page (`Media`, e.g. Pantheon)

Margin layout.

- Header row: poster in the left column (150px wide, optional, seeded from Notion; should not dominate). Middle: title; quiet metadata line ("TV series, 2022 to 2023, 2 seasons, 16 episodes. Cyberpunk, conspiracy thriller. Watched November 2022."); description; then "Edit description" and "Recheck tropes".
- Margin column in the header row: rating mark at 32px; a line of external links with scores where available ("Wikipedia · IMDb · TVDB · TMDB · Metacritic 77 · Rotten Tomatoes 100%"); local copy path in quiet text; "n of your posts mention 'Title'" linking to a search of Wasabi's Tumblr.
- Tropes grouped by prominence, same instance format as the trope page but the title is the trope name.
- After the list: 1px ink rule, "Add a trope" field with trope-name autocomplete and Add.
- Removed: "checked against 27", "Shares the most tropes with", the "text and evidence get drafted from the source" help line.

### 6.4 Library (`Library`)

The full log as a table.

- With no filters, show everything, newest first. Render the first 100 rows with a "Show all 778" link (or paginate/virtualise; the requirement is that all entries are reachable without filtering).
- Filters as plain text rows: Type (All, Book, TV, Movie, Game, Podcast, Album, Other), Trope (autocomplete text field) with a "Core theme only" toggle, Rating minimum (Any, 3+, 4+, 4.5+).
- Columns: Title (underlined link) with creator in quiet text, Type, Logged (year shown, **sorted by full date**, undated entries last), Rating (number then bars), Tropes.
- Tropes column: up to three trope names, core ones first and bold, then "+n". Should become links.
- "Show rating breakdown" toggles five extra sortable columns (Medium, Story, Tone, Enjoy, Effect). Off by default.
- A one-line quiet note under the table explains the bar order and that bold tropes are core themes.
- Genre and category filters were requested in the original brief but are not in the mockup yet; add them once genres come in from external metadata.

### 6.5 Add a trope (`AddTrope`)

Two steps, one page.

1. **Describe**: Name; Description ("A sentence or two. Write [[Trope name]] to link another trope."); Examples (one title per line, used to check the scan). Primary button: "Scan 778 entries". Cancel.
2. **Review the scan**: shows the description with an Edit link back to step 1, then a line reporting calibration, for example "Found all three of your examples, scoring 0.97, 0.90 and 0.81, plus four others. Anything under 0.5 starts unchecked." Then a list sorted by score: score in a left gutter; checkbox + media title; quiet type; "your example" in italic for seeds; prominence picker on the right; the `who` + text with an Edit link. Primary button "Commit n instances", plus "Change description and rescan" and "Discard".
3. **Done**: "Casual Necromancy is live with 6 instances." Link to the trope page or add another.

Nothing is saved until commit. Committed instances start unverified.

The seeds are the calibration check: if one of Wasabi's own examples scores low or doesn't appear, the description needs work.

### 6.6 Add a media item (`AddMedia`)

1. Type a title (year or type optional, for disambiguation). "Look it up".
2. Confirm what was found: canonical title; details (type, studio/network, air dates and episode count, genres); the Notion log entry if it exists; the local copy if found; a list of links with checkboxes and scores; "Add a link". Then tropes: every trope checked, matches listed with score, checkbox, prominence picker, `who` and text, plus a quiet line like "Checked against all 27. Two matched; nothing else scored above 0.3." Primary button "Add to library", plus "Wrong match" / "Start over".
3. Done, with a link to the new page.

Poster should be found and offered here too.

### 6.7 Recheck a trope (`Recheck`)

Reached from "Recheck instances" on a trope page. Deliberately almost identical to step 2 of Add a trope.

**Only proposes additions.** Two sections:

- **New instances**: same row format as the add flow, with evidence thumbnails.
- **New evidence for existing instances**: grouped by media, each proposed quote or frame with its own checkbox.

Primary button "Add n selected", plus Cancel. Never proposes removal, prominence changes, or edits to existing text.

### 6.8 Recheck a media item (`RecheckMedia`)

Reached from "Recheck tropes" on a media page. Same idea: **New tropes** (score, checkbox, prominence, text, evidence) and **New evidence for existing tropes**. Additions only.

### 6.9 Public trope page (`PublicTropeMargin`)

The trope page with all editing removed: no verification marks, no Edit links, no Recheck, no add form, no "Add trope/Add media" in the nav. Unverified instances appear exactly like verified ones. Spoilers work the same. Footer the same.

---

## 7. The matching pipeline

### 7.1 What the model reads

The trope's description is the prompt. Seed examples are given alongside as positive calibration. Wasabi's original definitions often include calibration notes in plain words ("Needs dog/collar/leash imagery; general animal imagery is an acceptable stretch"), and those belong in the description itself.

### 7.2 Two passes

Scanning ~780 works against a trope with full source text every time is expensive. Use two passes:

1. **Cheap pass** over every entry: title, synopsis/metadata, Wasabi's own notes and posts. Produces a candidate list with rough scores.
2. **Expensive pass** on candidates only: subtitles (transcribed or extracted), EPUB text, sampled frames. Produces the final score, prominence, `who`, text, and evidence.

Evidence extraction (quotes, screenshots, clips from local files) was acknowledged as the most expensive part to build, and that's accepted.

### 7.3 Scores

Each proposal gets a score from 0 to 1. Items under 0.5 start unchecked in add and recheck flows. The score is not shown on trope or media pages; prominence and verification are what readers see.

### 7.4 Rechecks

Rechecks run the same pipeline but only output additions: works not yet associated, and new evidence for existing associations. They never touch existing prominence, text, or associations.

---

## 8. Data sources

### 8.1 Notion Media Log (primary)

- Database "📖 Media Log", data source `collection://993327c5-6f33-4429-ad1a-88a0d603bded`, parent page "Home".
- Fields: `Title`, `Type` (Album, Book, Game, Movie, Other, Podcast, TV Series), `Artist/Developer`, `Medium`, `Story`, `Tone`, `Enjoyability`, `Effect` (numbers 0–5, rings), `Average Rating` (formula, not available via SQL), `Date` (date), `Image Link` (url), `Media Link` (url).
- 778 entries as of 19 October 2026.
- **Image Link** often points at theposterdb.com assets (e.g. `https://theposterdb.com/api/assets/263743` for Pantheon) or Goodreads covers. These download fine as 1000×1500 PNGs; resize for the page.
- **Media Link** often points at IMDb or Goodreads and is a good canonical-ID seed.
- Data quality notes found while building the library mock:
  - About 150 entries have no date (mostly older movies and shows logged without dates). Sort them last.
  - Many entries have no ratings at all; albums usually only have Medium; some games have partial ratings.
  - Duplicates and near-duplicates: "Leviathan Falls" (2018 unrated and 2021 rated), "Dispatches from Elsewhere" / "Dispatches From Elsewhere", "Much Ado About Nothing" (book and movie, which is fine), "The Princess Bride" (book and movie, fine), several Harry Potter titles as both book and movie (fine).
  - Typos in titles: "Warfarme", "Kerbal Space Prgram", "Thor: Ragnorak", "Beseige", "Borderlands: The Pre-Sequal", "Middle Earth: SOM". Matching against external sources should be fuzzy, and fixing these in Notion may be worth doing first.
  - Inconsistent naming: "Horizon: Zero Dawn" vs. the common "Horizon Zero Dawn"; "Friends at the Table: Twilight Mirage" vs. "Counterweight" and "Marielda" without the prefix.
- Wasabi prefers CSV export over the Notion API for bulk reads; either works.

### 8.2 External metadata

What worked and what didn't during research for the mockups:

- **Wikipedia**: reliable for premise, episode counts, air dates, Rotten Tomatoes and Metacritic aggregate scores.
- **MyAnimeList**: page fetches fine. Gives score, episodes, aired dates, studio, source, genres, themes, rating, and external links (AniDB, Anime News Network, Wikipedia, official site). Metallic Rouge is MAL id 54794, score 6.21.
- **IMDb**: blocks automated fetches (robots disallowed). Scores need another route: an API, a dataset dump, or skipping IMDb scores.
- **TheTVDB**: series pages exist at `thetvdb.com/series/<slug>`; probably use their API for episode data.
- **TMDB**: Pantheon is TV id 195339. Has an API and poster images.
- **Metacritic, Rotten Tomatoes, Goodreads, Steam, Letterboxd**: not tested. Expect scraping friction; prefer APIs where they exist.

The mockups show real values for Pantheon (IMDb tt11680642, 2 seasons, 16 episodes, AMC+ then Prime Video, Metacritic 77, Rotten Tomatoes 100%) and Metallic Rouge (Bones, original, aired January 11 to April 4, 2024, 13 episodes, Action and Sci-Fi, MAL 6.21).

### 8.3 Wasabi's writing

- Tumblr archive search at `beta.midden.net/api/search` with `blog:`, `tag:` and `date:` filters. The weekly posts are `blog:wasabipesto tag:mondayposting`.
- Unquoted common words time out ("matched too much to rank within 12s"). Quote the title: `"pantheon" blog:wasabipesto` returned 6 hits.
- Keyword hits are noisy. For Pantheon, several of the 6 are probably about the word, not the show ("Five Kinds of Elves", "Apokalypsis", a warlock patron post). Needs a relevance check before the count is shown, or show it only as a search link.
- Format and page size are gated behind an `x-api-key` Wasabi can provide.
- Annual media review posts on wasabipesto.com are another source of Wasabi's own commentary.

### 8.4 Local media

Books, movies, TV and so on are all stored locally, with a Plex server in the homelab. The exact library paths and layout weren't discussed; the mockups show `[library path]`. Pipeline needs: subtitle extraction or transcription for video, EPUB text extraction, frame sampling, clip cutting.

---

## 9. Writing rules for generated text

These apply to instance text, descriptions, and any copy the model writes.

- **Describe the work, not the process.** The text should read like the final reference entry. No mention of where an instance came from, what was approved, what is missing, or what will happen later. Forbidden examples from earlier drafts: "Added by hand from your list", "No reasoning yet; the next scan will write some", "Your other calibration example", "Weak match", "Probably a miss", "Kept so you can decide".
- **Remember what the reader already sees.** Prominence and verification are shown structurally, so the text never says how strong a match is. The `who` lead-in already names the characters, so the text doesn't repeat them pointlessly.
- **Verify facts or leave them out.** An early draft claimed Rouge depends on Naomi for Nectar; that was wrong. Research before stating plot facts, and ask Wasabi when the connection isn't findable (see open questions).
- **Plain prose.** Avoid the usual LLM tells: em-dashes as connectors, "not X but Y" contrasts, aphoristic closers, rule-of-three lists, inflated vocabulary, trailing "-ing" clauses. The humanizer skill (github.com/blader/humanizer) was the reference.
- **Spoilers go in `||bars||`,** at the smallest span that hides the spoiler.
- Wasabi's own words, where they exist, beat a rewrite. The Dog Duo description is Wasabi's original definition nearly verbatim.

---

## 10. Seed content

### 10.1 Mind, Machine, Divine, Animal tropes

From Wasabi's talk prep (October 2026). Definitions are Wasabi's; examples are Wasabi's original lists.

- **We Built Our Own Gods**: entities constructed by humans but far surpassing them in scope. Mrs. Davis, Friends at the Table's Divine cycle, Horizon Zero Dawn, Crystal Society; minor: American Gods.
- **Sapient Ship or Station**: something huge, powerful and physical that cares about the smaller things inside it, notably one that speaks and has agency. The Culture, ART (Murderbot), Lucy (Killjoys), GLaDOS (Portal), Ancillary Justice.
- **Sentient Construct**: a virtual entity that gained or was granted sentience, notably free to change its form since it has never had a physical body. Miku, Vibri, Cortana, MIST (Pantheon), Caine (The Amazing Digital Circus).
- **Sentient Android**: a machine that gained or was granted sentience and acts as a character with agency. BT-7274 (Titanfall 2), Rouge and Naomi (Metallic Rouge), Levi (Scavengers Reign), Nine/Ten/Juice (17776), Warframes, Loader Bot (TFTBL), Sarah and Tharmas (Unsong), Questionable Content, V1 (Ultrakill).
- **Uploaded Mind**: a person's mind copied or moved into a new permanent robot body, or someone who replaced their body with machinery. Ghost in the Shell, Citizen Sleeper, Viktor (Arcane), Pantheon.
- **Virtual Worlds**: a fully virtual world where the rules differ from ours, especially one where characters can shape it or themselves at will. Pantheon, Snow Crash, Cyberpunk, Permutation City, Diaspora.
- **It/Its Characters**: any character who uses it/its pronouns (or, in foreign works, characters without a gender). Sniper (Terra Ignota), Murderbot, Swarm (The Mercy of Gods), the Emperor (Baldur's Gate 3); minor: Nanachi (Made in Abyss).
- **Shapeshifters and Body Hoppers**: characters who can freely change their form to express themselves at will, and do so often. Mona (Dirk Gently's Holistic Detective Agency), the kandra (Mistborn).
- **Hive Mind and Unification**: a connection of minds, bleeding into one another until the boundaries between selves disappear. The cluster (Sense8), Viktor's commune (Arcane), SKABMOM (Unsong), Ninefox Gambit; minor: Heaven Will Be Mine.
- **Dog Duo**: see 10.3.
- **Soul Manipulation**: rigorous manipulation of souls: merging, splitting, building, editing. Examples not formally listed; Gideon the Ninth and Made in Abyss are placeholders in the mock.

### 10.2 Brainstormed tropes (19 October 2026)

Name, then Wasabi's examples. "Diagetic" was corrected to "Diegetic".

- The Big Misguided Plan to Save the World: Taravangian (Stormlight Archive), Darling Control
- Post-Gender Society: Diaspora, Terra Ignota
- Cooking the Monsters: Delicious in Dungeon, Monster Hunter
- Crafting the Monsters: Horizon. Should link [[Cooking the Monsters]] and vice versa.
- Space Truckers: Cowboy Bebop, The Expanse
- Diegetic Bangers: Control, Outer Wilds, The Martian, Into the Spider-Verse, The Fifth Element
- Multiple Timelines: Titanfall, Control 2
- Numbers for Names: 1000xRESIST
- Magic Gun: TBW, Control
- Conversation with the Author: The Erogamer, Unsong, Stranger than Fiction, The Egg, The Forgotten City
- Full-Screen Location Card: Control, Control 2, Avengers: Age of Ultron
- Vore and Unbirthing: Scavengers Reign, Mrs. Davis, American Gods
- Genre Savvy: Community, The Erogamer, Seven Psychopaths
- Arms Outstretched: Balance (The Adventure Zone), DAN DA DAN, Scott Pilgrim (opening)
- Magic Circles: Witch Hat Atelier, Fullmetal Alchemist
- Casual Necromancy: Pushing Daisies, Baldur's Gate 3, Neuromancer

Checked against the log on 19 October 2026: Monster Hunter, Darling Control, TBW and Control 2 have no log entry. The Stormlight Archive is logged as individual books, not a series. "Balance" is logged as "The Adventure Zone: Balance", Horizon as "Horizon: Zero Dawn", and Scott Pilgrim as "Scott Pilgrim Takes Off". Every other example has an entry.

Only Casual Necromancy got a full description in the mock: "Raising or talking to the dead is ordinary in the setting, cheap or routine or bureaucratic, and the characters treat it that way." That wording is a draft, not Wasabi's.

### 10.3 Dog Duo, worked example

Description (Wasabi's, lightly edited): "Two characters who are linked by something deeper than fate, with a very distinctive leashed but animalistic flavor. There is dog, collar or leash imagery somewhere in the pairing; general animal imagery is an acceptable stretch. When the bond stops being figurative it usually becomes [[Soul Manipulation]] or [[Hive Mind and Unification]]." Calibration from Wasabi: Zanj's circlet and lioness form count; Chise and Ruth count.

Instances in the mock (facts checked where noted):

- **Empress of Forever**, Viv and Zanj, Core. Viv holds Zanj, close to a god, through the circlet; Zanj's lioness form. (Wasabi's own calibration.)
- **Gideon the Ninth**, Gideon and Harrow, Core. Cavalier as sworn sword and guard dog. Spoiler: Gideon dies so Harrow can take her soul; they share a body in the sequel.
- **Metallic Rouge**, Rouge and Naomi, Core, unverified. Naomi is the Ministry agent assigned to keep Rouge on mission. Spoiler: Naomi gives Rouge her core, and in the finale transfers her consciousness into Rouge as her operating system. (Checked against Wikipedia.)
- **Almost Nowhere**, Sylvie and Grant, Core. Sylvie is an anomaling who comes into Grant's life playing his dog; far more powerful than the role. (Checked against a review; details thin.)
- **Terra Ignota**, Mycroft and Saladin, Recurring. Saladin as Mycroft's feral other half, tied to him by the murders they committed together.
- **The Ancient Magus' Bride**, Chise and Ruth, Recurring. Ruth is a church grim in the shape of a black dog; his life is tied to hers by contract.
- **DAN DA DAN**, Momo and Okarun, Brief, unverified. Text only says what could be confirmed. See open questions.

Recheck proposals in the mock: SPY x FAMILY (Anya and Bond, Brief) and The Owl House (Eda and the Owl Beast, Recurring).

### 10.4 Pantheon, worked media example

Tropes: Uploaded Mind (Core, verified), Virtual Worlds (Core, verified), Sentient Construct for MIST (Recurring, verified; MIST is a computational intelligence Caspian builds from what is left of David Kim's and Laurie Lowell's uploads, and she thinks of Maddie as her sister; season 2 spoiler, checked against Wikipedia), We Built Our Own Gods (Recurring, unverified). Recheck proposal: Casual Necromancy (Brief).

---

## 11. Decisions that were tried and rejected

So nobody rebuilds them:

- A dark theme with grotesque display type, amber accents, chips and panels. Too generic and too busy.
- A separate review queue page. Auto items live alongside the rest; verification is inline.
- A "drafts" section on the tropes index. Committing ends the add flow; there are no drafts.
- Collections of tropes. No clear purpose.
- "Matching prompt" shown as a separate block. The description is the prompt.
- Automatic rescan when a description is saved. Rescans are explicit.
- Rechecks that propose removals or prominence changes. Additions only.
- Brief instances collapsed by default.
- A "show all spoilers" toggle, and a block-level spoiler reveal button.
- Dark solid spoiler bars, and reveals that shift the layout.
- "Related tropes" lists. Use `[[links]]` in descriptions.
- "Shares the most tropes with" on media pages.
- "Checked against n tropes" on media pages.
- Count lines like "7 instances, 2 unverified" on trope pages.
- Help text explaining that text and evidence get drafted from the source.
- Writing out the five rating axes next to the bars.
- A confidence or "auto" badge on instances. Scores only appear in add and recheck flows.

---

## 12. Open questions

- **Tech stack and hosting.** Undecided. Wasabi's usual tools include Postgres, Rust, Astro and GCP/Cloudflare, and there's a homelab. Not decided here.
- **Public or private.** Possibly public, possibly just open source. The public page design is ready either way. If public, think about how much of a book can be quoted and how many frames shown per work; fair use generally favours short excerpts with commentary, but that was not researched.
- **Momo and Okarun (DAN DA DAN).** Wasabi listed them as a Dog Duo. The dog or leash imagery wasn't findable in research. Ask Wasabi what was meant before writing the instance text.
- **Notion Average Rating formula.** Match it rather than using a plain mean.
- **Local library layout.** Paths, formats, and what's already indexed (Plex metadata, subtitles).
- **Tumblr post counts.** Needs relevance filtering before the count is trustworthy.
- **IMDb scores.** Need a source other than scraping.
- **Genres and categories** in library filters, once external metadata is in.
- **Library trope names** should become links.
- **Narrow-screen spacing** in the margin layout needs another pass.
- **Series grouping** (Terra Ignota, Murderbot books, Stormlight) needs a model decision: does an instance attach to the series, to each book, or both?

---

## 13. The canvas

The Claude Design canvas "Trope Log" has these artboards, all interactive in Play mode with hardcoded data:

| Artboard | What it shows |
|---|---|
| Tropes index | Flat sortable table of all 27 tropes |
| Trope page: Dog Duo | Owner view, margin layout, inline editing, description editing |
| Recheck a trope | Additions-only recheck for Dog Duo |
| Media page: Pantheon | Owner view with poster, real links and scores, description editing |
| Library | All 778 log entries embedded from Notion, filters, sorting, rating bars |
| Add a trope | Describe, then review scan results (Casual Necromancy) |
| Add a media item | Look up and confirm (Metallic Rouge, real metadata) |
| Recheck a media item | Additions-only recheck for Pantheon |
| Public: Dog Duo | Public trope page, no editing controls |

Placeholders in brackets (`[timestamp]`, `ch. [n]`, `[library path]`, quoted passages) stand for content that needs the local files. Everything else on the Pantheon and Metallic Rouge pages and in the library is real data as of 19 October 2026.
