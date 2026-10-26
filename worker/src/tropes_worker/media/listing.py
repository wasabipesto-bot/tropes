"""What is on the media disk: a flat listing of the video folders, from a walk or from a saved `find` dump.

The media worker walks `/data` itself; for reports run elsewhere the same listing comes from
`find TV Movies Anime -printf "%y\\t%s\\t%TY-%Tm-%Td\\t%p\\n"`, so the matcher never needs the disk.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

VIDEO_EXT = {".mkv", ".mp4", ".m4v", ".avi", ".wmv", ".mov", ".webm", ".ts"}
SUB_EXT = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
VIDEO_TOPS = ("TV", "Movies", "Anime")
EPISODE_RX = re.compile(r"[. _-]S(\d{1,2})E(\d{1,3})(?:[-E](\d{1,3}))?", re.I)
SEASON_DIR_RX = re.compile(r"^(?:season|series)\s*(\d{1,2})\b|^S(\d{1,2})\b", re.I)


@dataclass
class Entry:
    path: str  # relative to the media root, posix
    is_dir: bool
    size: int = 0
    date: str = ""

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name

    @property
    def ext(self) -> str:
        return PurePosixPath(self.path).suffix.lower()


@dataclass
class Folder:
    """One work's folder under TV, Movies or Anime, with its video and subtitle files."""

    top: str
    name: str
    path: str
    videos: list[Entry] = field(default_factory=list)
    subs: list[Entry] = field(default_factory=list)

    @property
    def is_series(self) -> bool:
        return self.top in ("TV", "Anime")


@dataclass
class Listing:
    entries: list[Entry]

    @classmethod
    def from_find(cls, text: str) -> Listing:
        out = []
        for line in text.splitlines():
            parts = line.split("\t", 3)
            if len(parts) != 4 or parts[0] not in ("d", "f"):
                continue
            out.append(Entry(path=parts[3], is_dir=parts[0] == "d", size=int(parts[1] or 0), date=parts[2]))
        return cls(out)

    @classmethod
    def scan(cls, root: str, tops: tuple[str, ...] = VIDEO_TOPS) -> Listing:
        out = []
        for top in tops:
            base = os.path.join(root, top)
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                rel = os.path.relpath(dirpath, root)
                for d in dirnames:
                    out.append(Entry(path=f"{rel}/{d}", is_dir=True))
                for f in filenames:
                    try:
                        st = os.stat(os.path.join(dirpath, f))
                        out.append(Entry(path=f"{rel}/{f}", is_dir=False, size=st.st_size))
                    except OSError:
                        continue
        return cls(out)

    def folders(self) -> list[Folder]:
        """Work folders: the first level under each top, with every video and subtitle beneath them."""
        by_key: dict[tuple[str, str], Folder] = {}
        for e in self.entries:
            parts = e.path.split("/")
            if len(parts) < 2 or parts[0] not in VIDEO_TOPS:
                continue
            key = (parts[0], parts[1])
            folder = by_key.get(key)
            if folder is None:
                folder = by_key[key] = Folder(top=parts[0], name=parts[1], path=f"{parts[0]}/{parts[1]}")
            if e.is_dir:
                continue
            if e.ext in VIDEO_EXT:
                folder.videos.append(e)
            elif e.ext in SUB_EXT:
                folder.subs.append(e)
        return list(by_key.values())


def episode_of(path: str) -> tuple[int, int] | None:
    """(season, episode) from a file name like Show.S02E03.Title.mkv, else from a Season folder plus a bare number."""
    name = PurePosixPath(path).name
    m = EPISODE_RX.search(name)
    if m:
        return int(m.group(1)), int(m.group(2))
    parent = PurePosixPath(path).parent.name
    sm = SEASON_DIR_RX.match(parent)
    if sm:
        season = int(sm.group(1) or sm.group(2))
        em = re.search(r"(?:^|[ ._-])(?:e|ep|episode)?\s*(\d{1,3})(?=[ ._-]|$)", PurePosixPath(name).stem, re.I)
        if em:
            return season, int(em.group(1))
    return None


def sidecar_subs(video: Entry, subs: list[Entry]) -> list[Entry]:
    """Subtitle files beside a video that share its stem (Show.S01E01.en.srt for Show.S01E01.mkv)."""
    stem = PurePosixPath(video.path).with_suffix("").name.lower()
    parent = str(PurePosixPath(video.path).parent)
    out = []
    for s in subs:
        if str(PurePosixPath(s.path).parent) != parent:
            continue
        sstem = PurePosixPath(s.path).with_suffix("").name.lower()
        if sstem == stem or sstem.startswith(stem + "."):
            out.append(s)
    return out
