"""transcribe: Whisper for video sources that had no subtitle from any other source (plan D6, the fourth source).

Runs on the media worker, after extract_text has recorded a miss (`meta.textSource == "none"`). Audio is
decoded with ffmpeg to 16 kHz mono and transcribed with faster-whisper (`uv sync --extra whisper`; the
model downloads on first use into the Hugging Face cache). Payload {sourceIds?, auto, model?, threads?}:
without ids, every video source with a recorded miss. The text is rendered like a subtitle file, with the
segment's start as the stamp, and posted as source `whisper`.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..media import ffmpeg
from ..media.subtitles import Cue, render
from ..runner import Context
from .extract_text import episode_heading

log = logging.getLogger("tropes_worker.jobs.transcribe")


def wants_transcript(source: dict[str, Any]) -> bool:
    """A video file that extract_text looked at and found no subtitle for."""
    return (
        source.get("kind") == "video" and bool(source.get("indexedAt")) and (source.get("meta") or {}).get("textSource") == "none"
    )


def cues_from_segments(segments: Any) -> list[Cue]:
    """faster-whisper segments (start, end, text) as cues; empty and bracketed non-speech lines are dropped."""
    out: list[Cue] = []
    for s in segments:
        text = " ".join(str(s.text).split())
        if not text or (text.startswith(("[", "(")) and text.endswith(("]", ")"))):
            continue
        out.append(Cue(start=float(s.start), end=float(s.end), text=text))
    return out


def transcribe_file(path: Path, model: Any) -> list[Cue]:
    import numpy as np

    raw = ffmpeg.audio_f32(path)
    if not raw:
        return []
    audio = np.frombuffer(raw, dtype=np.float32)
    segments, _info = model.transcribe(audio, language="en", vad_filter=True, beam_size=1, condition_on_previous_text=False)
    return cues_from_segments(segments)


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    root = Path(settings.media_root or "")
    if not root.is_dir():
        raise RuntimeError(f"TROPES_MEDIA_ROOT is not a directory: {settings.media_root!r}")
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper is not installed on this worker: uv sync --extra whisper") from e
    wanted = set(payload.get("sourceIds") or [])
    todo: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for m in ctx.client.subjects()["media"]:
        for s in m.get("localSources") or []:
            if wanted and s["id"] not in wanted:
                continue
            if not wanted and not wants_transcript(s):
                continue
            todo.append((m, s))
    name = payload.get("model") or settings.whisper_model
    threads = int(payload.get("threads") or settings.whisper_threads)
    model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)
    done = failed = 0
    seconds = 0.0
    ctx.progress(0, len(todo), f"whisper {name}")
    for n, (m, s) in enumerate(todo, 1):
        path = root / s["path"]
        t0 = time.monotonic()
        try:
            cues = transcribe_file(path, model) if path.is_file() else []
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the batch
            log.warning("transcribe %s: %s", s["path"], e)
            cues = []
        took = time.monotonic() - t0
        seconds += took
        if cues:
            text = render(cues, episode_heading(m, s, path))
            ctx.client.post_source_text(s["id"], text, "whisper", {"whisperModel": name, "whisperSeconds": round(took)})
            done += 1
        else:
            failed += 1
        ctx.progress(n, len(todo), f"whisper {name}")
    return {
        "summary": {"sources": len(todo), "transcribed": done, "failed": failed, "model": name, "minutes": round(seconds / 60, 1)}
    }
