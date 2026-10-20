---
version: 2
---
Decide whether this work contains the trope exactly as described, and if so write the entry for it.

Trope: {{trope_name}}
{{trope_description}}

Works the owner gave as examples of this trope, which set the bar for what counts:
{{seeds}}

The work:
{{entry}}

Dossier:
{{dossier}}

{{text_section}}

Reply with JSON of this shape:
{"match": true or false, "score": 0.0 to 1.0, "prominence": "core|recurring|brief", "who": "the character, pair or element, like 'Viv and Zanj' or 'MIST'", "text": "one or two sentences in the site's voice", "evidence": [{"content": "an exact quotation copied from the supplied text", "locator": "chapter or section it comes from"}]}

Be strict. The description names specific things that must be present; a thematic cousin, a bond that is merely close, or a work that shares a mood with the examples is not a match. Most candidates that reach this step are not matches, and `match` false with a low score is the usual right answer. Scores: 0.9 or above only when you would stake money on it and could point to the scene; 0.7 to 0.9 when the trope is there but less central or less literal than in the owner's examples; below 0.5 when it is a stretch. Prominence: core when the trope drives the work, recurring when it is a major thread, brief when it is a scene, an arc or a nod. Evidence only when the work's text was supplied above: copy passages exactly, up to three, each under 100 words; otherwise return an empty list. Do not include the trope's name in the text.
