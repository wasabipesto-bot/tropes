---
version: 2
---
Build a dossier for one work from the owner's media log. The dossier is internal: later prompts read it to decide which tropes the work contains, so favour concrete, checkable detail over praise. A trope hunter needs to know who the characters are and how they relate, what imagery and objects recur, the shape of the plot, the themes, and scenes someone would point to.

Use everything you know about this work. If you know it well, say "strong" in `known`. If you only recognise the title or know it from secondary sources, say "partial" and keep to what you are sure of. If you do not know it at all, say "none" and fill in only what the log entry, notes and text below support.

Log entry:
{{entry}}

The owner's own notes about it (may be empty; may include reblogs or passing mentions, ignore anything plainly about something else):
{{notes}}

{{extract}}

{{text_section}}

Reply with JSON of this shape, and fill every list when you know the work:
{"known": "strong|partial|none",
 "summary": "one paragraph: premise, shape of the plot, ending in ||spoiler bars||",
 "characters": [{"name": "", "role": "protagonist, antagonist, mentor, the ship's AI, and so on", "descriptors": ["species or nature", "what they are called", "pronouns if notable", "appearance or imagery tied to them"], "relationships": ["bond with X: what kind, with the imagery used for it"]}],
 "settings": ["places, eras, institutions"],
 "arcs": [{"summary": "one plot thread, start to end", "locator": "chapters or episodes it spans, or null"}],
 "motifs": ["recurring images, objects, phrases, devices: leashes, circles, numbers for names, songs played in-world, that sort of thing"],
 "themes": ["..."],
 "notable_scenes": [{"summary": "a specific scene someone would cite", "locator": "chapter or episode, or null"}]}

For a work you know strongly, give every named character of consequence (usually 6 to 15), at least 6 motifs, and at least 6 notable scenes. When the text was supplied, locators must name the chapter heading as it appears in the text. Keep the whole dossier under about 1200 words.
