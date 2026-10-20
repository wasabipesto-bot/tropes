---
version: 1
---
Build one dossier for a series treated as a single work, from the dossiers of its parts. Merge characters and motifs that recur, keep arcs in order, and keep locators that name the part they come from.

Series: {{name}}
{{description}}

Dossiers of the parts, in order:
{{members}}

Reply with JSON of this shape:
{"known": "strong|partial|none", "summary": "one paragraph", "characters": [{"name": "", "role": "", "descriptors": ["..."], "relationships": ["..."]}], "settings": ["..."], "arcs": [{"summary": "", "locator": "which part"}], "motifs": ["..."], "themes": ["..."], "notable_scenes": [{"summary": "", "locator": "which part"}]}

Keep it under about 1200 words.
