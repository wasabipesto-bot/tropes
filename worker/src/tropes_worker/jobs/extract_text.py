"""extract_text: the text of each indexed file (plan T3, T4), posted to the site per local source.

Runs on the media worker. Video: an English sidecar subtitle, else an embedded English stream (plain
over SDH), else OpenSubtitles, else nothing (Whisper is a later, separate step). Books: EPUB through
the existing extractor, MOBI and AZW3 unpacked first. Payload {sourceIds?, auto}: without ids, every
local source not yet indexed.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..media import subtitles
from ..media.opensubtitles import OpenSubtitles
from ..runner import Context
from ..sources import _epub_to_marked, _txt_to_marked

log = logging.getLogger("tropes_worker.jobs.extract_text")


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.settings
    root = Path(settings.media_root or "")
    if not root.is_dir():
        raise RuntimeError(f"TROPES_MEDIA_ROOT is not a directory: {settings.media_root!r}")
    wanted = set(payload.get("sourceIds") or [])
    media = ctx.client.subjects()["media"]
    todo: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for m in media:
        for s in m.get("localSources") or []:
            if wanted and s["id"] not in wanted:
                continue
            if not wanted and s.get("indexedAt"):
                continue
            todo.append((m, s))
    os_client = None
    if settings.opensubtitles_key:
        os_client = OpenSubtitles(
            settings.opensubtitles_key,
            settings.opensubtitles_user,
            settings.opensubtitles_password,
            user_agent=settings.user_agent,
        )
        os_client.login()
    counts: dict[str, int] = {}
    ctx.progress(0, len(todo), "extracting")
    for n, (m, s) in enumerate(todo, 1):
        try:
            text, how = extract(root, m, s, os_client)
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the batch
            log.warning("extract %s: %s", s["path"], e)
            text, how = "", f"error: {type(e).__name__}"
        counts[how.split(":")[0]] = counts.get(how.split(":")[0], 0) + 1
        ctx.client.post_source_text(s["id"], text, how)
        if n % 10 == 0:
            ctx.progress(n, len(todo), "extracting")
    ctx.progress(len(todo), len(todo), "done")
    summary = {"sources": len(todo), **counts}
    if os_client and os_client.remaining is not None:
        summary["opensubtitlesRemaining"] = os_client.remaining
    return {"summary": summary}


def extract(root: Path, m: dict[str, Any], s: dict[str, Any], os_client: OpenSubtitles | None) -> tuple[str, str]:
    """(rendered text, how): how is sidecar | embedded | opensubtitles | epub | mobi | none."""
    path = root / s["path"]
    if s["kind"] == "book":
        return book_text(path)
    if s["kind"] != "video":
        return "", "none"
    heading = episode_heading(m, s, path)
    meta = s.get("meta") or {}
    for sub in meta.get("sidecars") or []:
        p = root / sub
        if p.is_file() and _looks_english(p.name):
            cues = subtitles.parse(p.read_text(encoding="utf-8", errors="replace"))
            if cues and subtitles.is_english(cues):
                return subtitles.render(cues, heading), "sidecar"
    streams = [
        st
        for st in meta.get("subtitleStreams") or []
        if (st.get("lang") or "eng") in ("eng", "en", "und")
        and st.get("codec") in ("subrip", "ass", "ssa", "webvtt", "mov_text", "text")
    ]
    streams.sort(
        key=lambda st: ("sdh" in (st.get("title") or "").lower() or "hearing" in (st.get("title") or "").lower(), st["index"])
    )
    for st in streams:
        raw = ffmpeg_subtitles(path, st["index"])
        cues = subtitles.parse(raw) if raw else []
        if cues and subtitles.is_english(cues):
            return subtitles.render(cues, heading), "embedded"
    if os_client:
        imdb = (m.get("externalIds") or {}).get("imdb")
        ep = _episode_numbers(s.get("label") or "")
        if imdb:
            raw = os_client.fetch(imdb, *ep) if ep else os_client.fetch(imdb)
            cues = subtitles.parse(raw) if raw else []
            if cues and subtitles.is_english(cues):
                return subtitles.render(cues, heading), "opensubtitles"
    return "", "none"


def episode_heading(m: dict[str, Any], s: dict[str, Any], path: Path) -> str:
    label = s.get("label") or ""
    if not label:
        return m["title"]
    # "Arcane.S01E01.Welcome.to.the.Playground.1080p.NF.WEB-DL…" → "Welcome to the Playground"
    stem = path.stem
    mm = re.search(
        r"S\d{1,2}E\d{1,3}[. _-]+(.*?)(?:[. _-](?:\d{3,4}p|WEB|BluRay|HDTV|x264|x265|HEVC|AAC|DDP|NF|AMZN|REPACK)\b.*)?$",
        stem,
        re.I,
    )
    name = re.sub(r"[._]+", " ", mm.group(1)).strip() if mm and mm.group(1) else ""
    return f"{label} {name}".strip()


def _episode_numbers(label: str) -> tuple[int, int] | None:
    mm = re.match(r"S(\d+)E(\d+)", label)
    return (int(mm.group(1)), int(mm.group(2))) if mm else None


def _looks_english(name: str) -> bool:
    low = name.lower()
    if re.search(r"\.(en|eng|english)(\.|$)", low):
        return True
    return not re.search(r"\.([a-z]{2,3})\.(srt|ass|ssa|vtt)$", low)  # no language tag at all: assume the main language


def ffmpeg_subtitles(path: Path, index: int) -> str | None:
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-map", f"0:{index}", "-f", "srt", "-"],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
            errors="replace",
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("ffmpeg subtitles %s stream %s: %s", path.name, index, e)
        return None
    return out


def book_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return _epub_to_marked(path), "epub"
    if suffix in (".mobi", ".azw3", ".azw"):
        import mobi  # KindleUnpack; imported here so the model worker never needs it

        with tempfile.TemporaryDirectory() as tmp:
            _, out = mobi.extract(str(path))
            out_path = Path(out)
            epubs = list(out_path.rglob("*.epub"))
            if epubs:
                text = _epub_to_marked(epubs[0])
            else:
                htmls = sorted(out_path.rglob("*.html")) + sorted(out_path.rglob("*.htm"))
                text = _html_to_marked(htmls)
            Path(tmp).mkdir(exist_ok=True)
        return text, "mobi"
    if suffix in (".txt", ".md"):
        return _txt_to_marked(path.read_text(encoding="utf-8", errors="replace")), "txt"
    return "", "none"


def _html_to_marked(files: list[Path]) -> str:
    from bs4 import BeautifulSoup

    from ..sources import CHAPTER_MARK

    parts = []
    for n, f in enumerate(files, 1):
        soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        body = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()
        if len(body.split()) < 20:
            continue
        for h in soup.find_all(["h1", "h2", "h3"]):
            title = re.sub(r"\s+", " ", h.get_text(" ")).strip()
            if title:
                body = body.replace(title, f"{CHAPTER_MARK}{title}\n", 1)
        parts.append(body if CHAPTER_MARK in body else f"{CHAPTER_MARK}Section {n}\n{body}")
    return "\n".join(parts).strip()
