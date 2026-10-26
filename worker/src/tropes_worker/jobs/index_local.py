"""index_local: match log entries to files under the media root and tell the site what each work has (plan T2).

Runs on the media worker, where the root is a local disk. Payload {mediaIds?, auto}. Video works
become one row per episode or film file with the subtitle streams and sidecar files noted; books
become one row pointing at the Calibre file to read. Ambiguous and year-mismatched matches are
reported, not recorded.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from ..media.listing import Listing, sidecar_subs
from ..media.match import best_video, calibre_rows, folder_index, match_book, match_video
from ..runner import Context

log = logging.getLogger("tropes_worker.jobs.index_local")


def probe_streams(path: Path) -> dict[str, Any]:
    """Subtitle and audio streams of a video file, from ffprobe; {} when ffprobe is missing or fails."""
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name:stream_tags=language,title:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    data = json.loads(out or "{}")
    subs = []
    for st in data.get("streams", []):
        if st.get("codec_type") != "subtitle":
            continue
        tags = st.get("tags", {})
        subs.append(
            {"index": st["index"], "codec": st.get("codec_name"), "lang": tags.get("language"), "title": tags.get("title")}
        )
    duration = data.get("format", {}).get("duration")
    return {"duration": round(float(duration)) if duration else None, "subtitleStreams": subs}


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    root = settings.media_root
    if not root or not Path(root).is_dir():
        raise RuntimeError(f"TROPES_MEDIA_ROOT is not a directory: {root!r}")
    wanted = set(payload.get("mediaIds") or [])
    media = [m for m in ctx.client.subjects()["media"] if (not wanted or m["id"] in wanted)]
    media = [m for m in media if m["type"] in ("TV Series", "Movie", "Book")]
    ctx.progress(0, len(media) + 1, "listing the disk")
    listing = Listing.scan(root)
    folders = listing.folders()
    index = folder_index(folders)
    calibre_path = Path(root) / "Books" / "metadata.db"
    calibre = sqlite3.connect(f"file:{calibre_path}?mode=ro", uri=True) if calibre_path.is_file() else None
    rows = calibre_rows(calibre) if calibre else []

    works: list[dict[str, Any]] = []
    report = {"ok": 0, "none": 0, "ambiguous": 0, "year": 0, "books": 0, "episodes": 0, "films": 0}
    unmatched: list[str] = []
    checks: list[dict[str, Any]] = []
    done = 0
    for m in media:
        done += 1
        if done % 25 == 0:
            ctx.progress(done, len(media) + 1, "matching")
        details = m.get("details") or {}
        start = str(details.get("start") or "")
        year = int(start[:4]) if start[:4].isdigit() else None
        if m["type"] == "Book":
            b = (
                match_book(
                    {"title": m["title"], "creator": m.get("creator"), "externalIds": m.get("externalIds") or {}}, calibre, rows
                )
                if calibre
                else None
            )
            file = b.file() if b else None
            if not b or not file:
                report["none"] += 1
                unmatched.append(m["title"])
                continue
            report["books"] += 1
            works.append(
                {
                    "mediaId": m["id"],
                    "sources": [
                        {
                            "kind": "book",
                            "path": file,
                            "label": "",
                            "meta": {"calibreId": b.book_id, "formats": b.formats, "by": b.by},
                        }
                    ],
                }
            )
            continue
        matches = match_video({"title": m["title"], "type": m["type"], "year": year}, folders, index)
        best, why = best_video(matches)
        if not best:
            report[why if why in report else "none"] += 1
            if why == "none":
                unmatched.append(m["title"])
            else:
                checks.append(
                    {"mediaId": m["id"], "title": m["title"], "why": why, "folders": [x.folder.path for x in matches[:3]]}
                )
            continue
        report["ok"] += 1
        sources = []
        if m["type"] == "TV Series":
            for season, episode, entry in best.episodes:
                meta = probe_streams(Path(root) / entry.path)
                meta["sidecars"] = [s.path for s in sidecar_subs(entry, best.folder.subs)]
                sources.append({"kind": "video", "path": entry.path, "label": f"S{season:02d}E{episode:02d}", "meta": meta})
            report["episodes"] += len(sources)
        else:
            if best.films:
                entry = best.films[0]
                meta = probe_streams(Path(root) / entry.path)
                meta["sidecars"] = [s.path for s in sidecar_subs(entry, best.folder.subs)]
                sources.append({"kind": "video", "path": entry.path, "label": "", "meta": meta})
                report["films"] += 1
        if sources:
            works.append({"mediaId": m["id"], "sources": sources})
    for i in range(0, len(works), 50):
        ctx.client.post_sources(works[i : i + 50])
    ctx.progress(len(media) + 1, len(media) + 1, "done")
    warnings = [f"not on the disk: {', '.join(unmatched[:60])}"] if unmatched else []
    warnings += [f"check: {c['title']} ({c['why']}): {', '.join(c['folders'])}" for c in checks[:40]]
    return {"summary": {**report, "checks": len(checks)}, "warnings": warnings}
