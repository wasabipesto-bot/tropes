"""look_frames: for a scan's proposals of visual tropes, the model looks at the frames grabbed at the quoted
moments and says whether the trope is actually in the picture (plan D12). The site lowers the score of
proposals where it is not and shows the verdict as a flag on the review page."""

from __future__ import annotations

import base64
import logging
from typing import Any

from ..llm import LLM
from ..pipeline import run_async
from ..runner import Context
from ..schemas import LookOut

log = logging.getLogger("tropes_worker.jobs.look_frames")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    return run_async(_run(ctx, payload))


async def _run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    items = ctx.client.frames_for(int(payload["forJob"]))
    llm = LLM(ctx.settings)
    done = 0
    ctx.progress(0, len(items), "looking at frames")

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        images = []
        captions = []
        for f in item["frames"][:4]:
            data = ctx.client.pending_frame(item["proposalId"], f["name"])
            if data:
                images.append(base64.b64encode(data).decode())
                captions.append(f"{len(images)}. {f.get('locator') or ''}: “{(f.get('content') or '')[:160]}”")
        done += 1
        ctx.progress(done, len(items), "looking at frames")
        if not images:
            return {"proposalId": item["proposalId"], "seen": True, "note": "no frame could be read"}
        out = await llm.complete(
            "look_frame",
            {
                "trope_name": item["trope"]["name"],
                "trope_description": item["trope"]["description"],
                "who": item.get("who") or "",
                "text": item.get("text") or "",
                "captions": "\n".join(captions),
            },
            LookOut,
            images=images,
        )
        return {"proposalId": item["proposalId"], "seen": out.seen, "note": out.note.strip()[:200]}

    verdicts = await llm.gather([one(i) for i in items])
    seen = sum(1 for v in verdicts if v["seen"])
    return {"summary": {"looked": len(verdicts), "seen": seen}, "verdicts": verdicts, "usage": llm.usage.as_dict()}
