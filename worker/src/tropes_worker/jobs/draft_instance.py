"""draft_instance: the owner added an association with a title and a note; the model writes it (plan: seeds-and-quick-add).

Payload {instanceId, note}. Reads the trope, the work's dossier and, when the work has one, its text (the block
the note points at for long works); writes who, the entry and the prominence in the site's voice, and up to three
verbatim quotes checked against the text. The text lands on the instance (unverified); the quotes attach as
evidence like a Find's, and frames follow.
"""

from __future__ import annotations

from typing import Any

from ..llm import LLM
from ..pipeline import (
    LazyTexts,
    cap_chars,
    dossier_block,
    ensure_texts,
    entry_text,
    load_subject_text,
    polish,
    run_async,
    subject_key,
    text_for_pass2,
    verify_quotes,
)
from ..runner import Context
from ..schemas import Pass2Out
from ..sources import text_section


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    instance_id = int(payload["instanceId"])
    note = (payload.get("note") or "").strip()
    tropes = ctx.client.tropes()
    hit = next(((t, i) for t in tropes for i in t.get("instances", []) if i["id"] == instance_id), None)
    if hit is None:
        return {"summary": {"written": 0}, "warnings": ["That association no longer exists."]}
    trope, inst = hit
    exported = ctx.client.subjects()
    media, series = exported["media"], exported["series"]
    subject = next((s for s in [*media, *series] if s["kind"] == inst["kind"] and s["id"] == inst["subjectId"]), None)
    if subject is None:
        return {"summary": {"written": 0}, "warnings": ["The work no longer exists."]}
    ensure_texts(
        ctx.client,
        settings,
        [subject] if subject["kind"] == "media" else [m for m in media if m["id"] in subject.get("members", [])],
    )
    dossiers = {subject_key(d["subjectKind"], d["subjectId"]): d for d in ctx.client._get("/api/dossiers")["dossiers"]}
    key = subject_key(subject["kind"], subject["id"])
    text = load_subject_text(settings, subject, LazyTexts(settings, media))
    if text is not None and len(text.full) > cap_chars(settings):
        text = text_for_pass2(settings, text, note or trope.get("description") or "", dossiers.get(key))

    ctx.progress(0, 1, "writing")
    llm = LLM(settings)
    seeds = ", ".join(s["title"] for s in trope.get("seeds") or []) or "(none)"
    out = await llm.complete(
        "draft_instance",
        {
            "trope_name": trope["name"],
            "trope_description": trope.get("description") or "",
            "seeds": seeds,
            "entry": entry_text(subject),
            "note": note or "(none)",
            "dossier": dossier_block(dossiers, key),
            "text_section": text_section(text),
        },
        Pass2Out,
    )
    text_out, flags = await polish(llm, out.text)
    evidence, dropped = verify_quotes(text, out.evidence)
    warnings = list(flags)
    if dropped:
        warnings.append(f"{dropped} quote{'s' if dropped > 1 else ''} not found in the text and dropped")
    if text is None:
        warnings.append("No text of the work is available; the entry rests on the dossier and what the model knows.")
    proposals = [
        {
            "tropeId": trope["id"],
            "subject": {"kind": inst["kind"], "id": inst["subjectId"]},
            "kind": "evidence",
            "targetInstanceId": instance_id,
            "score": 1.0,
            "who": out.who.strip(),
            "text": "",
            "evidence": [q],
            "seed": False,
            "rejectedBefore": False,
            "flags": [],
        }
        for q in evidence
    ]
    return {
        "summary": {"written": 1, "quotes": len(evidence), "hasText": text is not None, "prominence": out.prominence},
        "rewrites": [
            {
                "instanceId": instance_id,
                "who": out.who.strip() or (inst.get("who") or ""),
                "text": text_out.strip(),
                "prominence": out.prominence,
                "flags": flags,
            }
        ],
        "proposals": proposals,
        "usage": llm.usage.as_dict(),
        "warnings": warnings,
    }
