# Proposed Notion title clean-up

Reviewed 2026-10-19 against the 778 entries embedded in the Library artboard (same data as Notion on 19 October). Nothing has been changed in Notion. Approve, strike or amend lines here; the approved set gets applied through the Notion API by a script that matches on the exact current title, so edits made in Notion in the meantime are safe.

Tier A is a typo. Tier C is the work's official title or consistency with its neighbours; these are judgment calls and skipping any of them is fine. The machine-readable copy is `notion-title-fixes.json`.

## Titles

| Tier | Current | Proposed | Why |
|---|---|---|---|
| A | Warfarme | Warframe | typo |
| A | Kerbal Space Prgram | Kerbal Space Program | typo |
| A | Thor: Ragnorak | Thor: Ragnarok | typo |
| A | Beseige | Besiege | typo |
| A | Borderlands: The Pre-Sequal | Borderlands: The Pre-Sequel | typo |
| A | Middle Earth: SOM | Middle-earth: Shadow of Mordor | abbreviation and hyphen |
| C | Horizon: Zero Dawn | Horizon Zero Dawn | official title has no colon |
| C | Too Like The Lightning | Too Like the Lightning | capitalisation |
| C | Valerian and The City of a Thousand Planets | Valerian and the City of a Thousand Planets | capitalisation |
| C | Everything Everywhere All At Once | Everything Everywhere All at Once | capitalisation |
| C | There is No Antimemetics Division | There Is No Antimemetics Division | capitalisation |
| C | Bojack Horseman | BoJack Horseman | official spelling |
| C | Bioshock | BioShock | official spelling; the log already has BioShock Infinite |
| C | K-Pop Demon Hunters | KPop Demon Hunters | official spelling |
| C | Bocchi the Rock | Bocchi the Rock! | official title |
| C | What If? | What If...? | official title |
| C | Red White and Royal Blue | Red, White & Royal Blue | official title |
| C | Dungeons and Dragons: Honor Among Thieves | Dungeons & Dragons: Honor Among Thieves | official title |
| C | Mr. and Mrs. Smith | Mr. & Mrs. Smith | official title |
| C | Knives Out: Glass Onion | Glass Onion: A Knives Out Mystery | official title |
| C | The Matrix: Reloaded | The Matrix Reloaded | official title has no colon |
| C | The Matrix: Revolutions | The Matrix Revolutions | official title has no colon |
| C | The Matrix: Resurrections | The Matrix Resurrections | official title has no colon |
| C | Rogue One | Rogue One: A Star Wars Story | official title; matches Solo: A Star Wars Story |
| C | Star Wars | Star Wars: A New Hope | consistency with the other Star Wars entries |
| C | The Elder Scrolls: Skyrim | The Elder Scrolls V: Skyrim | official title |
| C | XCOM | XCOM: Enemy Unknown | official title; XCOM 2 is already specific |
| C | Hades 2 | Hades II | official title |
| C | Saints Row 3 | Saints Row: The Third | official title |
| C | Saints Row 4 | Saints Row IV | official title |
| C | Player of Games | The Player of Games | official title |
| C | Counterweight | Friends at the Table: Counterweight | prefix consistency with Twilight Mirage and Partizan |
| C | Marielda | Friends at the Table: Marielda | prefix consistency with Twilight Mirage and Partizan |

## Artist/Developer

| Title | Current | Proposed | Why |
|---|---|---|---|
| Jackrabbit | Sam Fermin | San Fermin | artist name is San Fermin |
| Dungeons and Dragons: Honor Among Thieves | Jonathan Goldstein and John Francis | Jonathan Goldstein and John Francis Daley | surname cut off |
| The Gay and Wondrous Life of Caleb Gallo | Youtube | YouTube | spelling |
| The Earth Is Not a Cold Dead Place | Explosions in The Sky | Explosions in the Sky | capitalisation |
| Vices and Virtues | Panic! At the Disco | Panic! at the Disco | capitalisation |
| Death of a Bachelor | Panic! At the Disco | Panic! at the Disco | capitalisation |

## Duplicates (decide, not auto-fixed)

- **Dispatches from Elsewhere** (TV, logged 2026-09-30, unrated) and **Dispatches From Elsewhere** (TV, 2020, rated). Same show twice with different capitalisation. If the 2026 one is a rewatch, keep both and fix the capitalisation of the older one; if it is a duplicate, delete one.
- **Leviathan Falls** twice: one rated at 2021, one unrated dated 2019 between *Seveneves* and *Tiamat's Wrath*. The book came out in 2021, so the 2019 entry is probably a mislabel. Delete it or rename it to whatever was actually read then.
- *The Princess Bride*, *Much Ado About Nothing* and the Harry Potter titles exist as both book and film. Intentional, left alone.

## Style choice: apostrophes

8 titles use a typographic apostrophe (’) and 36 use a straight one ('). Examples: *Baldur’s Gate 3* versus *The Ancient Magus' Bride*. The site will display whichever is stored. Options: (a) leave as is, (b) normalise all to straight in Notion and let the site render typographic ones, (c) normalise all to typographic. I lean to (b): straight is easier to type and search, and the site owns typography. Not applied without a decision.

## Left alone on purpose

- Stylised capitalisation the publisher uses (DREDGE, SUPERHOT, DAN DA DAN, 1000xRESIST) and cases where the log is already consistent with the official form.
- Titles with optional subtitles (*Potion Craft*, *Backfirewall*, *Dr. Langeskov*, *Magic Kingdom for Sale*, *The Final Empire*). Harmless either way; external lookup in Phase 4 will still match.
- Disambiguated entries like *Dune (1984)* and *3 Body Problem (2024)*: the parenthetical is useful and the site can keep it in the title or move it to metadata later.
- Creator fields that hold a network or studio instead of a person for TV and film. That is how the log has always been kept; the site treats it as a display string.
