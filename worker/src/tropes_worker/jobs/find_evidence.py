"""find_evidence: the owner names the moment they want quoted; the model finds it in the work's text.

Payload {instanceId, prompt}. Quotes are checked verbatim against the text and come back as
evidence proposals on the instance, which the site attaches at once. Without a text for the work
there is nothing to search, and the job says so.
"""

from __future__ import annotations

from typing import Any

from ..llm import LLM
from ..pipeline import ensure_texts, entry_text, load_subject_text, run_async, verify_quotes
from ..runner import Context
from ..schemas import EvidenceOut


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    instance_id = payload["instanceId"]
    prompt = payload["prompt"].strip()
    tropes = ctx.client.tropes()
    hit = next(((t, i) for t in tropes for i in t.get("instances", []) if i["id"] == instance_id), None)
    if hit is None:
        return {"summary": {"found": 0}, "warnings": ["That instance no longer exists."]}
    trope, inst = hit
    exported = ctx.client.subjects()
    media, series = exported["media"], exported["series"]
    ensure_texts(ctx.client, settings, media)
    subject = next((s for s in [*media, *series] if s["kind"] == inst["kind"] and s["id"] == inst["subjectId"]), None)
    if subject is None:
        return {"summary": {"found": 0}, "warnings": ["The work no longer exists."]}

    texts_by_media: dict[int, Any] = {}
    if subject["kind"] == "series":
        for mid in subject.get("members", []):
            m = next((x for x in media if x["id"] == mid), None)
            if m and m.get("textSources"):
                t = load_subject_text(settings, m)
                if t:
                    texts_by_media[mid] = t
    text = load_subject_text(settings, subject, texts_by_media)
    if text is None:
        title = subject.get("title") or subject.get("name")
        return {
            "summary": {"found": 0, "hasText": False},
            "warnings": [f"No text of {title} is available yet, so there is nothing to search."],
        }

    ctx.progress(0, 1, "searching")
    llm = LLM(settings)
    out = await llm.complete(
        "find_evidence",
        {
            "trope_name": trope["name"],
            "trope_description": trope["description"],
            "who": inst.get("who") or "",
            "text": inst.get("text") or "",
            "request": prompt,
            "entry": entry_text(subject),
            "text_section": f"The full text of the work follows, with `## ` chapter headings:\n\n{text.full}",
        },
        EvidenceOut,
    )
    kept, dropped = verify_quotes(text, out.evidence)
    proposals = [
        {
            "tropeId": trope["id"],
            "subject": {"kind": inst["kind"], "id": inst["subjectId"]},
            "kind": "evidence",
            "targetInstanceId": instance_id,
            "score": 1.0,
            "who": inst.get("who") or "",
            "text": "",
            "evidence": [q],
            "seed": False,
            "rejectedBefore": False,
            "flags": [],
        }
        for q in kept[:3]
    ]
    ctx.progress(1, 1, "done")
    warnings = []
    if not kept:
        warnings.append(
            "Nothing in the text matched that closely enough to quote."
            if not dropped
            else f"{dropped} candidate quote(s) were not in the text verbatim and were dropped."
        )
    return {
        "summary": {"found": len(proposals), "hasText": True, "request": prompt},
        "proposals": proposals,
        "usage": llm.usage.as_dict(),
        "warnings": warnings,
    }
