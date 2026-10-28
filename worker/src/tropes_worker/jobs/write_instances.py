"""write_instances: the entry text for trope instances that have none (or a placeholder), written from the work's
dossier in the site's voice. Runs on the model worker; one call per instance plus the writing check.

Payload {instanceIds?, auto}: without ids, every instance with an empty or placeholder text whose work has a
text-depth dossier (the owner's rule: only where the dossier is fresh and detailed). The site stores the text,
marks the instance unverified and lists it on /review.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..llm import LLM
from ..pipeline import dossier_block, entry_text, polish, run_async, subject_key
from ..runner import Context
from ..schemas import RewriteInstanceOut

log = logging.getLogger("tropes_worker.jobs.write_instances")

PLACEHOLDER_RX = re.compile(r"placeholder", re.I)


def needs_text(inst: dict[str, Any]) -> bool:
    return (
        not (inst.get("text") or "").strip()
        or bool(PLACEHOLDER_RX.search(inst.get("text") or ""))
        or bool(PLACEHOLDER_RX.search(inst.get("who") or ""))
    )


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    wanted = set(payload.get("instanceIds") or [])
    tropes = ctx.client.tropes()
    subjects = ctx.client.subjects()
    media = {m["id"]: m for m in subjects["media"]}
    dossiers = {subject_key(d["subjectKind"], d["subjectId"]): d for d in ctx.client._get("/api/dossiers")["dossiers"]}
    todo: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for t in tropes:
        for inst in t.get("instances") or []:
            if wanted and inst["id"] not in wanted:
                continue
            if inst.get("kind") != "media" or (not wanted and not needs_text(inst)):
                continue
            m = media.get(inst["subjectId"])
            d = dossiers.get(subject_key("media", inst["subjectId"]))
            if not m or not d or (not wanted and d.get("depth") != "text"):
                continue
            todo.append((t, inst, m))
    llm = LLM(settings)
    done = 0
    ctx.progress(0, len(todo), "writing")

    async def one(t: dict[str, Any], inst: dict[str, Any], m: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        seeds = ", ".join(s["title"] for s in t.get("seeds") or []) or "(none)"
        out = await llm.complete(
            "rewrite_instance",
            {
                "trope_name": t["name"],
                "trope_description": t.get("description") or "",
                "seeds": seeds,
                "entry": entry_text(m),
                "dossier": dossier_block(dossiers, subject_key("media", m["id"])),
                "who": inst.get("who") or "(not given)",
                "prominence": inst.get("prominence") or "brief",
            },
            RewriteInstanceOut,
        )
        text, flags = await polish(llm, out.text)
        done += 1
        ctx.progress(done, len(todo), "writing")
        return {"instanceId": inst["id"], "who": (out.who or inst.get("who") or "").strip(), "text": text.strip(), "flags": flags}

    got, warnings = await llm.gather_safely([one(t, i, m) for t, i, m in todo], "instance")
    rewrites = [r for r in got if r and r["text"]]
    return {
        "summary": {"instances": len(todo), "written": len(rewrites), "failed": len(warnings)},
        "rewrites": rewrites,
        "usage": llm.usage.as_dict(),
        "warnings": warnings[:40],
    }
