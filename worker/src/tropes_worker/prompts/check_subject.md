---
version: 1
---
Check one work against every trope in the catalogue. For each trope decide whether the work contains it and, if so, write the entry.

The work:
{{entry}}

Dossier:
{{dossier}}

{{text_section}}

Tropes, each with its id, description and the owner's example works:
{{tropes}}

Reply with JSON: {"items": [{"trope_id": <id>, "match": true or false, "score": 0.0 to 1.0, "prominence": "core|recurring|brief", "who": "", "text": "", "evidence": [{"content": "exact quotation from the supplied text", "locator": ""}]}]}. Include every trope once; most will be false with a low score and empty fields. Prominence: core when the trope drives the work, recurring for a major thread, brief for a scene or a nod. Evidence only when the text was supplied, copied exactly, up to three per trope, each under 100 words. Do not include the trope's name in the text.
