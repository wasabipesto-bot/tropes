---
version: 1
---
The owner has just said that this work contains this trope. The association is decided; write the entry for it: who or what it is about, one or two sentences in the site's voice on how the trope appears and why it counts, the prominence, and up to three exact quotations from the supplied text when a text is supplied. Use the owner's note as the steer for what to look at.

Trope: {{trope_name}}
{{trope_description}}
The owner's other examples of this trope: {{seeds}}

The work:
{{entry}}

The owner's note: {{note}}

Dossier:
{{dossier}}

{{text_section}}

Reply with JSON of this shape:
{"match": true, "score": 1.0, "prominence": "core|recurring|brief", "who": "the character, pair or element, like 'Vi and Jinx' or 'MIST'", "text": "one or two sentences; ||double bars|| around a spoiler", "evidence": [{"content": "an exact quotation copied from the supplied text", "locator": "chapter or section it comes from"}]}

Prominence: core when the trope drives the work, recurring when it is a major thread, brief when it is a scene, an arc or a nod. Evidence only when the work's text was supplied above: copy passages exactly, each under 100 words; otherwise return an empty list. Do not name the trope in the text.
