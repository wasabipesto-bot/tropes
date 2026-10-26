"""make_sheets: contact sheets for video sources (plan T11), uploaded to the site for the model worker to read.

Runs on the media worker. Payload {sourceIds?, auto}: without ids, every indexed video source that has
no sheets yet. One sheet per 45 minutes of running time, keyframes every 45 s, 10×6 tiles of 288 px.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..media import ffmpeg
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.make_sheets")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    root = Path(settings.media_root or "")
    if not root.is_dir():
        raise RuntimeError(f"TROPES_MEDIA_ROOT is not a directory: {settings.media_root!r}")
    wanted = set(payload.get("sourceIds") or [])
    todo: list[dict[str, Any]] = []
    for m in ctx.client.subjects()["media"]:
        for s in m.get("localSources") or []:
            if s.get("kind") != "video":
                continue
            if wanted and s["id"] not in wanted:
                continue
            if not wanted and (s.get("meta") or {}).get("sheets"):
                continue
            todo.append(s)
    made = failed = 0
    ctx.progress(0, len(todo), "sheets")
    for n, s in enumerate(todo, 1):
        path = root / s["path"]
        duration = (s.get("meta") or {}).get("duration")
        sheets = ffmpeg.sheets(path, float(duration) if duration else None) if path.is_file() else []
        if not sheets:
            failed += 1
        for i, data in enumerate(sheets):
            try:
                ctx.client.upload_sheet(s["id"], i, data)
                made += 1
            except Exception as e:  # noqa: BLE001 - keep going through the batch
                log.warning("sheet upload %s/%s: %s", s["id"], i, e)
                failed += 1
        if n % 5 == 0:
            ctx.progress(n, len(todo), "sheets")
    ctx.progress(len(todo), len(todo), "done")
    return {"summary": {"sources": len(todo), "sheets": made, "failed": failed}}
