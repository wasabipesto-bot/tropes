"""check_subject: one work (or series) against every trope. Add and recheck share it."""

from __future__ import annotations

from typing import Any

from ..llm import LLM
from ..pipeline import TropeSpec, build_dossier, check_subject, load_subject_text, new_evidence, run_async, subject_key
from ..runner import Context


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    ref = payload["subject"]
    tropes = ctx.client.tropes()
    exported = ctx.client.subjects()
    media, series = exported["media"], exported["series"]
    subject = next(s for s in [*media, *series] if s["kind"] == ref["kind"] and s["id"] == ref["id"])
    llm = LLM(settings)
    warnings: list[str] = []

    texts_by_media: dict[int, Any] = {}
    if subject["kind"] == "series":
        for mid in subject.get("members", []):
            m = next((x for x in media if x["id"] == mid), None)
            if m and m.get("textSources"):
                t = load_subject_text(settings, m)
                if t:
                    texts_by_media[mid] = t
    text = load_subject_text(settings, subject, texts_by_media)

    key = subject_key(subject["kind"], subject["id"])
    existing = ctx.client.dossier(subject["kind"], subject["id"])
    dossiers: dict[str, dict[str, Any]] = {}
    new_dossiers: list[dict[str, Any]] = []
    ctx.progress(0, 3, "dossier")
    if existing:
        dossiers[key] = existing
    elif subject["kind"] == "media":
        d = await build_dossier(llm, settings, subject, text, subject.get("notes") or [])
        dossiers[key] = {"body": d["body"]}
        new_dossiers.append(d)
    else:
        warnings.append("no dossier for this series yet; checked from its entry alone")

    # Existing instances for this subject (own only; inherited series instances count as covered too).
    existing_ids: set[int] = set()
    existing_insts: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for t in tropes:
        for i in t.get("instances", []):
            if i["kind"] == ref["kind"] and i["subjectId"] == ref["id"]:
                existing_ids.add(t["id"])
                existing_insts.append((t, i))

    ctx.progress(1, 3, "checking tropes")
    proposals = await check_subject(llm, settings, subject, dossiers, tropes, text, existing_ids)

    evidence_added = 0
    if payload.get("mode") == "recheck" and text is not None and existing_insts:

        async def more() -> list[dict[str, Any]]:
            out = []
            for t, inst in existing_insts:
                spec = TropeSpec(id=t["id"], name=t["name"], description=t["description"], seeds=[])
                for q in await new_evidence(llm, spec, inst, [], text):
                    out.append(
                        {
                            "tropeId": t["id"],
                            "subject": ref,
                            "kind": "evidence",
                            "targetInstanceId": inst["id"],
                            "score": 1.0,
                            "who": inst.get("who", ""),
                            "text": "",
                            "evidence": [q],
                            "seed": False,
                            "rejectedBefore": False,
                            "flags": [],
                        }
                    )
            return out

        extra = await more()
        evidence_added = len(extra)
        proposals += extra

    ctx.progress(3, 3, "done")
    dropped = sum(1 for p in proposals for f in p["flags"] if "not found in the text" in f)
    if dropped:
        warnings.append(f"{dropped} proposal{'s' if dropped > 1 else ''} had quotes dropped because they were not in the text")
    summary = {
        "subject": subject.get("title") or subject.get("name"),
        "checked": len(tropes) - len(existing_ids),
        "matched": len([p for p in proposals if p["kind"] == "instance"]),
        "evidence": evidence_added,
        "hasText": text is not None,
        "uncheckedBelow": settings.unchecked_below,
    }
    return {
        "summary": summary,
        "proposals": proposals,
        "dossiers": new_dossiers,
        "usage": llm.usage.as_dict(),
        "warnings": warnings,
    }
