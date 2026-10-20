"""scan_trope: pass 1 over every subject, pass 2 on the candidates. Add and recheck share it."""

from __future__ import annotations

import logging
from typing import Any

from ..llm import LLM
from ..pipeline import (
    Candidate,
    TropeSpec,
    choose_candidates,
    load_subject_text,
    new_evidence,
    pass1,
    pass2,
    run_async,
    subject_key,
)
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.scan_trope")


def resolve_title(title: str, media: list[dict[str, Any]], series: list[dict[str, Any]]) -> str | None:
    t = title.strip().lower()
    for s in series:
        if s["name"].lower() == t:
            return subject_key("series", s["id"])
    for m in media:
        if m["title"].lower() == t:
            return subject_key("media", m["id"])
    return None


def trope_spec_from(
    payload: dict[str, Any], tropes: list[dict[str, Any]], media: list[dict[str, Any]], series: list[dict[str, Any]]
) -> tuple[TropeSpec, list[str]]:
    """Build the spec from an existing trope id or the draft in the payload. Returns (spec, unresolved seed titles)."""
    unresolved: list[str] = []
    if payload.get("tropeId"):
        t = next(x for x in tropes if x["id"] == payload["tropeId"])
        spec = TropeSpec(id=t["id"], name=t["name"], description=t["description"], seeds=[s["title"] for s in t.get("seeds", [])])
        spec.existing = {subject_key(i["kind"], i["subjectId"]): i for i in t.get("instances", [])}
        # A series instance covers its members, so members are not re-proposed on their own.
        for s in series:
            if subject_key("series", s["id"]) in spec.existing:
                for m in s.get("members", []):
                    spec.existing.setdefault(subject_key("media", m), {"inherited": True})
        spec.rejected = {subject_key(r["kind"], r["id"]) for r in t.get("rejected", [])}
    else:
        d = payload["draft"]
        spec = TropeSpec(id=None, name=d["name"], description=d["description"], seeds=list(d.get("seeds", [])))
    for title in spec.seeds:
        key = resolve_title(title, media, series)
        if key:
            spec.seed_subjects.add(key)
        else:
            unresolved.append(title)
    return spec, unresolved


async def scan(
    ctx_like: Any,
    settings: Any,
    llm: LLM,
    spec: TropeSpec,
    subjects: list[dict[str, Any]],
    dossiers: dict[str, dict[str, Any]],
    texts_by_media: dict[int, Any],
    progress,
) -> tuple[list[dict[str, Any]], dict[str, tuple[float, str]], list[Candidate]]:  # noqa: ANN001
    scores = await pass1(llm, settings, spec, subjects, dossiers, progress)
    cands = choose_candidates(settings, spec, subjects, scores)

    async def all_pass2() -> list[dict[str, Any] | None]:
        async def one(c: Candidate):  # noqa: ANN202
            text = load_subject_text(settings, c.subject, texts_by_media)
            return await pass2(llm, settings, spec, c, dossiers, text)

        return await llm.gather([one(c) for c in cands])

    results = await all_pass2()
    proposals = [p for p in results if p]
    return proposals, scores, cands


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    tropes = ctx.client.tropes()
    exported = ctx.client.subjects()
    media, series = exported["media"], exported["series"]
    spec, unresolved = trope_spec_from(payload, tropes, media, series)
    dossiers = {subject_key(d["subjectKind"], d["subjectId"]): d for d in ctx.client._get("/api/dossiers")["dossiers"]}
    llm = LLM(settings)
    warnings = [f"seed example not in the library: {t}" for t in unresolved]

    # Subjects: every media item plus every series. Members of a series stay scannable on their own.
    subjects = [*media, *series]
    texts_by_media: dict[int, Any] = {}
    for m in media:
        if m.get("textSources"):
            t = load_subject_text(settings, m)
            if t:
                texts_by_media[m["id"]] = t

    total_steps = len(subjects) + 1
    ctx.progress(0, total_steps, "pass 1")
    proposals, scores, cands = await scan(
        ctx, settings, llm, spec, subjects, dossiers, texts_by_media, lambda d, t, n: ctx.progress(d, total_steps, n)
    )

    # Rechecks: new evidence for existing instances where a text exists.
    evidence_added = 0
    if payload.get("mode") == "recheck" and spec.existing:

        async def more_evidence() -> list[dict[str, Any]]:
            out = []

            async def one(key: str, inst: dict[str, Any]):  # noqa: ANN202
                kind, sid = key.split(":")
                subject = next((s for s in subjects if s["kind"] == kind and s["id"] == int(sid)), None)
                if not subject:
                    return
                text = load_subject_text(settings, subject, texts_by_media)
                if not text:
                    return
                quotes = await new_evidence(llm, spec, inst, inst.get("quotes", []), text)
                for q in quotes:
                    out.append(
                        {
                            "tropeId": spec.id,
                            "subject": {"kind": kind, "id": int(sid)},
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

            await llm.gather([one(k, i) for k, i in spec.existing.items()])
            return out

        extra = await more_evidence()
        evidence_added = len(extra)
        proposals += extra

    ctx.progress(total_steps, total_steps, "done")
    # When a series is proposed, its members' own proposals are redundant.
    proposed_series = {p["subject"]["id"] for p in proposals if p["kind"] == "instance" and p["subject"]["kind"] == "series"}
    covered = {m for s in series if s["id"] in proposed_series for m in s.get("members", [])}
    proposals = [
        p
        for p in proposals
        if not (p["kind"] == "instance" and p["subject"]["kind"] == "media" and p["subject"]["id"] in covered)
    ]

    seed_report = []
    for title in spec.seeds:
        key = resolve_title(title, media, series)
        found = None
        if key:
            found = next(
                (
                    p
                    for p in proposals
                    if p["kind"] == "instance" and subject_key(p["subject"]["kind"], p["subject"]["id"]) == key
                ),
                None,
            )
        seed_report.append(
            {
                "title": title,
                "resolved": key is not None,
                "attached": bool(key and key in spec.existing),
                "found": found is not None,
                "score": found["score"] if found else None,
                "pass1": scores.get(key, (None, ""))[0] if key else None,
            }
        )
    dropped = sum(1 for p in proposals for f in p["flags"] if "not found in the text" in f)
    if dropped:
        warnings.append(f"{dropped} proposal{'s' if dropped > 1 else ''} had quotes dropped because they were not in the text")
    summary = {
        "trope": spec.name,
        "scanned": len(subjects),
        "candidates": len(cands),
        "proposals": len([p for p in proposals if p["kind"] == "instance"]),
        "evidence": evidence_added,
        "seeds": seed_report,
        "uncheckedBelow": settings.unchecked_below,
    }
    return {"summary": summary, "proposals": proposals, "usage": llm.usage.as_dict(), "warnings": warnings}
