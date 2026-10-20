"""Build dossiers for every subject that needs one; post them in batches so a crash keeps progress."""

from __future__ import annotations

import logging
from typing import Any

from ..llm import LLM, load_prompt
from ..notes import relevant_notes, search_posts
from ..pipeline import build_dossier, build_series_dossier, dossier_needed, entry_text, load_subject_text, run_async
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.build_dossiers")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    only_missing = payload.get("onlyMissing", True)
    wanted = {(s["kind"], s["id"]) for s in payload.get("subjects") or []}
    exported = ctx.client.subjects()
    media = exported["media"]
    series = exported["series"]
    llm = LLM(settings)
    version = load_prompt("dossier").version
    warnings: list[str] = []

    todo: list[tuple[dict[str, Any], Any]] = []
    for s in media:
        if wanted and ("media", s["id"]) not in wanted:
            continue
        text = load_subject_text(settings, s)
        if only_missing and not wanted and not dossier_needed(s, version, text is not None, text.source_hash if text else None):
            continue
        todo.append((s, text))

    total = len(todo) + len(series)
    done = 0
    built = 0
    notes_total = 0
    ctx.progress(0, total, "dossiers")

    async def one(subject: dict[str, Any], text) -> tuple[dict[str, Any], list[dict[str, Any]]]:  # noqa: ANN001
        posts = search_posts(settings, subject["title"]) if subject["kind"] == "media" else []
        notes = await relevant_notes(llm, entry_text(subject), posts) if posts else []
        dossier = await build_dossier(llm, settings, subject, text, notes or subject.get("notes") or [])
        return dossier, [{"mediaId": subject["id"], "source": "tumblr", "url": n.get("url"), "text": n["text"]} for n in notes]

    async def batch(items: list[tuple[dict[str, Any], Any]]) -> None:
        nonlocal done, built, notes_total
        results = await llm.gather([one(s, t) for s, t in items])
        ctx.client._post("/api/dossiers", {"dossiers": [d for d, _ in results], "notes": [n for _, ns in results for n in ns]})
        built += len(results)
        notes_total += sum(len(ns) for _, ns in results)
        done += len(items)
        ctx.progress(done, total, "dossiers")

    for i in range(0, len(todo), 20):
        await batch(todo[i : i + 20])

    # Series after members, from fresh member dossiers.
    if series:
        all_dossiers = {(d["subjectKind"], d["subjectId"]): d for d in ctx.client._get("/api/dossiers")["dossiers"]}
        series_todo = [
            s
            for s in series
            if (not wanted or ("series", s["id"]) in wanted)
            and (not only_missing or wanted or dossier_needed(s, load_prompt("series_dossier").version, False, None))
        ]

        async def series_batch(items: list[dict[str, Any]]) -> None:
            nonlocal done, built
            results = []
            for s in items:
                members = [all_dossiers[("media", m)]["body"] for m in s.get("members", []) if ("media", m) in all_dossiers]
                if not members:
                    warnings.append(f"series {s['name']}: no member dossiers yet")
                    continue
                results.append(await build_series_dossier(llm, settings, s, members))
            if results:
                ctx.client._post("/api/dossiers", {"dossiers": results, "notes": []})
            built += len(results)
            done += len(items)
            ctx.progress(done, total, "series dossiers")

        for i in range(0, len(series_todo), 10):
            await series_batch(series_todo[i : i + 10])
        done = total
        ctx.progress(done, total, "done")

    return {
        "summary": {"built": built, "notes": notes_total, "skipped": len(media) - len(todo)},
        "usage": llm.usage.as_dict(),
        "warnings": warnings,
    }
