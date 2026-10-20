---
version: 3
---
Decide whether this work contains the trope as described, and if so write the entry for it.

Trope: {{trope_name}}
{{trope_description}}

The owner's own examples of this trope. They set the bar: a work that fits the description the way these do is a match; a work that only rhymes with them is not.
{{seeds}}

The work:
{{entry}}

Dossier:
{{dossier}}

{{text_section}}

Reply with JSON of this shape:
{"match": true or false, "score": 0.0 to 1.0, "prominence": "core|recurring|brief", "who": "the character, pair or element, like 'Viv and Zanj' or 'MIST'", "text": "one or two sentences in the site's voice", "evidence": [{"content": "an exact quotation copied from the supplied text", "locator": "chapter or section it comes from"}]}

Scoring, anchored to the examples above: 0.9 or above means it belongs beside them without argument; 0.7 to 0.9 means it fits the description, perhaps less centrally or less literally; 0.5 to 0.7 means a real but partial fit the owner might keep; below 0.5 means a stretch or a thematic cousin, and `match` should be false. The description names specific things that must be present; sharing a mood with the examples is not enough. Prominence: core when the trope drives the work, recurring when it is a major thread, brief when it is a scene, an arc or a nod. Evidence only when the work's text was supplied above: copy passages exactly, up to three, each under 100 words; otherwise return an empty list. Do not include the trope's name in the text.
