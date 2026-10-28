"""read_sheets: the model looks at each contact sheet and writes down what is shown but never said (plan T11).

Runs on the model worker. Payload {sourceIds?, auto}: without ids, every video source with sheets and
no visual note yet. One call per sheet; the notes for an episode's sheets are joined into one
media_note with source `visual` and the episode's label, which the dossier prompt reads.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from ..llm import LLM
from ..pipeline import run_async
from ..runner import Context
from ..schemas import VisualNotesOut

log = logging.getLogger("tropes_worker.jobs.read_sheets")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    wanted = set(payload.get("sourceIds") or [])
    todo: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for m in ctx.client.subjects()["media"]:
        have = {n.get("label") or "" for n in (m.get("notes") or []) if n.get("source") == "visual"}
        for s in m.get("localSources") or []:
            if s.get("kind") != "video" or not (s.get("meta") or {}).get("sheets"):
                continue
            if wanted and s["id"] not in wanted:
                continue
            if not wanted and (s.get("label") or "") in have:
                continue
            todo.append((m, s))
    llm = LLM(settings)
    done = 0
    ctx.progress(0, len(todo), "reading sheets")

    async def one(m: dict[str, Any], s: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal done
        count = int((s.get("meta") or {}).get("sheets") or 0)
        parts: list[str] = []
        for i in range(count):
            data = ctx.client.sheet(s["id"], i)
            if not data:
                continue
            out = await llm.complete(
                "visual_notes",
                {"entry": f"{m['title']} ({m.get('type')}), {s.get('label') or 'the whole work'}", "n": 60, "every": 45},
                VisualNotesOut,
                images=[base64.b64encode(data).decode()],
            )
            if out.notes:
                parts.append("\n".join(f"- {line.strip()}" for line in out.notes if line.strip()))
        done += 1
        ctx.progress(done, len(todo), "reading sheets")
        if not parts:
            return None
        return {"mediaId": m["id"], "source": "visual", "label": s.get("label") or "", "text": "\n".join(parts)[:6000]}

    # In batches: thousands of sources at once would download every sheet before the first model call and
    # leave the job silent past the queue's stale window; a batch of 40 posts its notes and a heartbeat as it goes.
    notes: list[dict[str, Any]] = []
    warnings: list[str] = []
    for i in range(0, len(todo), 40):
        batch, bad = await llm.gather_safely([one(m, s) for m, s in todo[i : i + 40]], "sheet")
        warnings += bad
        got = [r for r in batch if r]
        if got:
            ctx.client._post("/api/dossiers", {"dossiers": [], "notes": got})
            notes += got
        ctx.progress(min(i + 40, len(todo)), len(todo), "reading sheets")
    return {
        "summary": {"sources": len(todo), "notes": len(notes), "failed": len(warnings)},
        "notes": [],
        "usage": llm.usage.as_dict(),
        "warnings": warnings[:40],
    }
