"""extract_evidence: a frame (or a clip) at each timestamped quote, uploaded to the site (plan T6).

Runs on the media worker. Payload {items: [{proposalId|evidenceId, sourceId, at, end?, clip}]}. For a
proposal the picture waits beside the quote on the review page; for an evidence row it goes straight
onto the instance. Audio sources get an audio clip.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..media import ffmpeg
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.extract_evidence")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    root = Path(settings.media_root or "")
    if not root.is_dir():
        raise RuntimeError(f"TROPES_MEDIA_ROOT is not a directory: {settings.media_root!r}")
    sources: dict[int, dict[str, Any]] = {}
    for m in ctx.client.subjects()["media"]:
        for s in m.get("localSources") or []:
            sources[s["id"]] = s
    items = payload["items"]
    done = failed = 0
    ctx.progress(0, len(items), "frames")
    for n, it in enumerate(items, 1):
        s = sources.get(it["sourceId"])
        if not s:
            failed += 1
            continue
        path = root / s["path"]
        at = float(it["at"])
        end = float(it.get("end") or at + 12)
        if it.get("clip"):
            data = (
                ffmpeg.audio_clip(path, max(0, at - 2), end + 2)
                if s["kind"] == "audio"
                else ffmpeg.clip(path, max(0, at - 2), end + 2)
            )
            kind, ext = "clip", "mp4"
        else:
            data = ffmpeg.frame(path, at + 0.5)
            kind, ext = "frame", "webp"
        if not data:
            failed += 1
            continue
        target = f"proposal:{it['proposalId']}" if it.get("proposalId") else f"evidence:{it['evidenceId']}"
        try:
            ctx.client.upload_evidence(target, kind, at, data, ext)
            done += 1
        except Exception as e:  # noqa: BLE001 - one failed upload must not stop the batch
            log.warning("upload %s: %s", target, e)
            failed += 1
        if n % 5 == 0:
            ctx.progress(n, len(items), "frames")
    ctx.progress(len(items), len(items), "done")
    return {"summary": {"items": len(items), "done": done, "failed": failed}}
