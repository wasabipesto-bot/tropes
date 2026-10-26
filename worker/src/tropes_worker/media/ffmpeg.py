"""ffmpeg on the media worker: a frame, a short clip, a contact sheet. Output goes to memory, never beside the source."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("tropes_worker.media.ffmpeg")

FRAME_WIDTH = 640
CLIP_WIDTH = 640
CLIP_MAX = 30.0
SHEET_EVERY = 45  # seconds between contact-sheet shots (plan T11, the owner's 40–60 s)
SHEET_COLS, SHEET_ROWS, SHEET_TILE = 10, 6, 288


def _run(args: list[str], timeout: int) -> bytes | None:
    try:
        return subprocess.run(["ffmpeg", "-v", "error", *args], capture_output=True, timeout=timeout, check=True).stdout or None
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("ffmpeg %s: %s", " ".join(args[:6]), getattr(e, "stderr", b"")[:200] or e)
        return None


def frame(path: Path, at: float) -> bytes | None:
    """One WebP frame at `at` seconds, 640 px wide."""
    return _run(
        [
            "-ss",
            f"{at:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={FRAME_WIDTH}:-2",
            "-f",
            "image2",
            "-c:v",
            "libwebp",
            "-quality",
            "82",
            "-",
        ],
        120,
    )


def clip(path: Path, start: float, end: float) -> bytes | None:
    """An H.264 mp4 with audio from start to end (capped at 30 s), 640 px wide, playable in a browser."""
    length = max(1.0, min(CLIP_MAX, end - start))
    return _run(
        [
            "-ss",
            f"{start:.3f}",
            "-i",
            str(path),
            "-t",
            f"{length:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "26",
            "-vf",
            f"scale={CLIP_WIDTH}:-2",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-sn",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "-",
        ],
        300,
    )


def audio_clip(path: Path, start: float, end: float) -> bytes | None:
    """For podcasts: an m4a snippet, same cap."""
    length = max(1.0, min(CLIP_MAX, end - start))
    return _run(
        [
            "-ss",
            f"{start:.3f}",
            "-i",
            str(path),
            "-t",
            f"{length:.3f}",
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "-",
        ],
        120,
    )


def sheets(path: Path, duration: float | None) -> list[bytes]:
    """Contact sheets of keyframes every SHEET_EVERY seconds, SHEET_COLS×SHEET_ROWS tiles each; one per 45 minutes."""
    per_sheet = SHEET_COLS * SHEET_ROWS
    span = per_sheet * SHEET_EVERY
    count = (
        max(1, int((duration or span) // span) + (1 if duration and duration % span > SHEET_EVERY * 10 else 0)) if duration else 1
    )
    out = []
    for i in range(count):
        data = _run(
            [
                "-skip_frame",
                "nokey",
                "-ss",
                f"{i * span}",
                "-i",
                str(path),
                "-t",
                f"{span}",
                "-vf",
                f"fps=1/{SHEET_EVERY},scale={SHEET_TILE}:-2,tile={SHEET_COLS}x{SHEET_ROWS}:padding=2:color=black",
                "-frames:v",
                "1",
                "-f",
                "image2",
                "-c:v",
                "mjpeg",
                "-q:v",
                "4",
                "-",
            ],
            600,
        )
        if data:
            out.append(data)
    return out
