"""Subtitles into text the matcher can read and quote with timestamps (plan T3).

A cue becomes one line, `[12:40] line`, under a `## S01E03 Title` heading per episode; a series is
one text in episode order, a film one text. Cleaning drops tags, sound descriptions, music notes
and the duplicate lines SDH tracks carry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pysubs2

TAG_RX = re.compile(r"<[^>]+>|\{[^}]*\}")
BRACKET_RX = re.compile(r"\[[^\]]*\]|\([^)]*\)")  # [door slams], (sighs)
MUSIC_RX = re.compile(r"[♪♫]+")
SPEAKER_RX = re.compile(r"^[A-Z][A-Z .'-]{1,24}:\s+")  # SDH speaker label "JAYCE: Hello"
DASH_RX = re.compile(r"(?m)^\s*-\s*")
# ASS drawing commands ("m -437.5 42.33 b -437.67 42.5 …") that pysubs2 leaves in the plain text of typesetting lines.
DRAWING_RX = re.compile(r"\b[mnlbspc](?:\s+-?\d+(?:\.\d+)?){2,}")
# Styles fansubs use for signs, songs and karaoke rather than dialogue.
SIGN_STYLE_RX = re.compile(r"sign|song|kara|lyric|\bop\b|\bed\b|title|typeset|\bts\b|logo|credit", re.I)


@dataclass
class Cue:
    start: float  # seconds
    end: float
    text: str


def parse(text: str, fmt: str | None = None) -> list[Cue]:
    """Cues from SRT, ASS/SSA or WebVTT text, cleaned; empty ones dropped."""
    try:
        subs = pysubs2.SSAFile.from_string(text, format_=fmt) if fmt else pysubs2.SSAFile.from_string(text)
    except Exception:  # noqa: BLE001 - a malformed file is "no subtitles" rather than a crash
        return []
    cues: list[Cue] = []
    for ev in subs.events:
        if getattr(ev, "is_comment", False) or ev.type != "Dialogue":
            continue
        raw = ev.text or ""
        # Typesetting: drawing mode, or a style named for signs and songs. Dialogue never draws.
        if "\\p1" in raw or "\\p2" in raw or "\\p4" in raw or SIGN_STYLE_RX.search(getattr(ev, "style", "") or ""):
            continue
        line = clean(ev.plaintext if hasattr(ev, "plaintext") else raw)
        if line:
            cues.append(Cue(ev.start / 1000, ev.end / 1000, line))
    cues.sort(key=lambda c: c.start)
    # Layered or per-frame repeats of the same line (signs re-rendered every frame) collapse into one cue.
    out: list[Cue] = []
    for c in cues:
        if out and out[-1].text == c.text and c.start - out[-1].start < 2.0:
            out[-1].end = max(out[-1].end, c.end)
            continue
        out.append(c)
    return out


def clean(raw: str) -> str:
    s = raw.replace("\\N", "\n").replace("\\n", "\n")
    s = TAG_RX.sub("", s)
    s = DRAWING_RX.sub("", s)
    s = MUSIC_RX.sub("", s)
    s = BRACKET_RX.sub("", s)
    lines = []
    for part in s.splitlines():
        part = DASH_RX.sub("", part.strip())
        part = SPEAKER_RX.sub("", part)
        if part:
            lines.append(part)
    return re.sub(r"\s+", " ", " ".join(lines)).strip(" -–—")


def is_english(cues: list[Cue], sample: int = 200) -> bool:
    """A cheap guard: most short English function words should appear in a sample of cues."""
    text = " ".join(c.text for c in cues[:sample]).lower()
    words = set(re.findall(r"[a-z']+", text))
    hits = sum(w in words for w in ("the", "you", "and", "it", "to", "i", "a", "that", "of", "is", "what", "we"))
    return hits >= 6


def stamp(seconds: float) -> str:
    """12:40, or 1:02:05 past the hour."""
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def render(cues: list[Cue], heading: str | None = None, *, merge_gap: float = 1.0) -> str:
    """One line per cue with its timestamp; consecutive cues under a second apart that read as one
    sentence are joined so quotes are not cut mid-sentence."""
    out: list[str] = []
    if heading:
        out.append(f"## {heading}")
    buf: list[str] = []
    buf_start = 0.0
    prev_end = -10.0

    def flush() -> None:
        if buf:
            out.append(f"[{stamp(buf_start)}] {' '.join(buf)}")
            buf.clear()

    for c in cues:
        joinable = buf and c.start - prev_end <= merge_gap and not re.search(r"[.!?…\"”]$", buf[-1])
        if not joinable:
            flush()
            buf_start = c.start
        buf.append(c.text)
        prev_end = c.end
    flush()
    return "\n".join(out)


def parse_stamp(s: str) -> float | None:
    """Seconds from "12:40" or "1:02:05", as written in the rendered text; None when it is not a stamp."""
    m = re.match(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*$", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def srt_from_cues(cues: list[Cue]) -> str:
    """Back to SRT (for the cache and for ffmpeg), in case a stream was extracted as ASS."""
    subs = pysubs2.SSAFile()
    for c in cues:
        subs.events.append(pysubs2.SSAEvent(start=int(c.start * 1000), end=int(c.end * 1000), text=c.text))
    return subs.to_string("srt")
