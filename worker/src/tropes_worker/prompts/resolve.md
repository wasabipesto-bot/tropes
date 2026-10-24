---
version: 1
---
Decide which public work a media-log entry refers to. The candidates come from Wikidata; a deterministic match could not separate them. Use the type, the creator, the year the owner logged it (the work cannot have come out after that) and what you know about these works.

Log entry:
{{entry}}

Candidates:
{{candidates}}

Reply with JSON: {"choice": "<the candidate's id, or null when none of them is this work>", "confidence": <0 to 1>, "why": "<one short sentence>"}
