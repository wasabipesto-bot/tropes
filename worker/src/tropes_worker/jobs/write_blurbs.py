"""write_blurbs: a two- or three-sentence description draft per work, from its dossier and Wikipedia extract (plan D15/D20)."""

from __future__ import annotations

import json
import re
from typing import Any

from ..llm import LLM
from ..pipeline import entry_text, polish, run_async
from ..runner import Context
from ..schemas import RewriteOut

# A model that does not know the work says so instead of describing it; that is not a description.
NON_ANSWER = re.compile(
    r"\b(I do not know|I don't know|cannot describe|can't describe|no information|unknown title|not familiar)\b", re.I
)


def usable(text: str) -> bool:
    return bool(text.strip()) and not NON_ANSWER.search(text) and len(text.split()) >= 8


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    wanted = set(payload["mediaIds"])
    media = [m for m in ctx.client.subjects()["media"] if m["id"] in wanted]
    dossiers = {d["subjectId"]: d["body"] for d in ctx.client._get("/api/dossiers")["dossiers"] if d["subjectKind"] == "media"}
    llm = LLM(ctx.settings)
    done = 0
    ctx.progress(0, len(media), "blurbs")

    async def one(m: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal done
        body = dossiers.get(m["id"])
        dossier = (
            json.dumps({k: body[k] for k in ("summary", "themes", "settings") if k in body}, ensure_ascii=False)
            if body
            else "(none)"
        )
        extract = m.get("wikiExtract") or "(none)"
        # Nothing to write from: no dossier worth the name and no encyclopaedia summary.
        if (body is None or body.get("known") == "none") and extract == "(none)":
            done += 1
            return None
        out = await llm.complete("blurb", {"entry": entry_text(m), "dossier": dossier, "extract": extract[:2000]}, RewriteOut)
        text, _flags = await polish(llm, out.text.strip())
        done += 1
        ctx.progress(done, len(media), "blurbs")
        return {"mediaId": m["id"], "text": text} if usable(text) else None

    results = await llm.gather([one(m) for m in media])
    descriptions = [r for r in results if r]
    return {
        "summary": {"written": len(descriptions), "skipped": len(media) - len(descriptions)},
        "descriptions": descriptions,
        "usage": llm.usage.as_dict(),
    }
