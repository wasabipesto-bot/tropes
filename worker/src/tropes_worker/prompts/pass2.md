---
version: 1
---
Decide whether this work contains the trope, and if so write the entry for it.

Trope: {{trope_name}}
{{trope_description}}

Works the owner gave as examples of this trope:
{{seeds}}

The work:
{{entry}}

Dossier:
{{dossier}}

{{text_section}}

Reply with JSON of this shape:
{"match": true or false, "score": 0.0 to 1.0, "prominence": "core|recurring|brief", "who": "the character, pair or element, like 'Viv and Zanj' or 'MIST'", "text": "one or two sentences in the site's voice", "evidence": [{"content": "an exact quotation copied from the supplied text", "locator": "chapter or section it comes from"}]}

Prominence: core when the trope drives the work, recurring when it is a major thread, brief when it is a scene, an arc or a nod. `match` false with a low score is a fine answer. Evidence only when the work's text was supplied above: copy passages exactly, up to three, each under 100 words; otherwise return an empty list. Do not include the trope's name in the text.
