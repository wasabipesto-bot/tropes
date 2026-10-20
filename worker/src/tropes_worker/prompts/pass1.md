---
version: 1
---
Score how likely each work below contains the trope. This is a first pass over summaries; be generous on recall, the next pass reads the actual work. Use your own knowledge of each work as well as its dossier.

Trope: {{trope_name}}
{{trope_description}}

Works the owner gave as examples of this trope (treat these as the calibration of what counts):
{{seeds}}

Works to score, each with its dossier:
{{batch}}

Reply with JSON: {"items": [{"subject": "<the subject key exactly as given>", "score": 0.0 to 1.0, "reason": "under 20 words"}]}. Include every subject once. 0.0 means clearly absent, 0.5 means plausible but unsure, 1.0 means certainly present and central.
