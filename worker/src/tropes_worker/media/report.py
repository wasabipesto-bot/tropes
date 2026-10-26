"""`tropes-worker media match`: which works have files, which need a look, which are not on the disk. Writes nothing."""

from __future__ import annotations

import gzip
import sqlite3
from collections import Counter
from pathlib import Path

from ..client import SiteClient
from ..settings import Settings
from .listing import Listing
from .match import best_video, calibre_rows, folder_index, match_book, match_video


def match_report(settings: Settings, client: SiteClient, *, root: str | None, listing: str | None, calibre: str | None) -> str:
    root = root or settings.media_root
    if listing:
        text = (
            gzip.open(listing, "rt", errors="replace").read()
            if listing.endswith(".gz")
            else Path(listing).read_text(errors="replace")
        )
        lst = Listing.from_find(text)
    elif root:
        lst = Listing.scan(root)
    else:
        raise SystemExit("give --root or --listing (or set TROPES_MEDIA_ROOT)")
    folders = lst.folders()
    index = folder_index(folders)
    cal_path = calibre or (f"{root}/Books/metadata.db" if root else None)
    cal = sqlite3.connect(f"file:{cal_path}?mode=ro", uri=True) if cal_path and Path(cal_path).is_file() else None
    rows = calibre_rows(cal) if cal else []
    media = client.subjects()["media"]
    counts: dict[str, Counter] = {}
    lines: dict[str, list[str]] = {"check": [], "none": []}
    for m in media:
        t = m["type"]
        if t == "Book":
            if not cal:
                continue
            b = match_book(
                {"title": m["title"], "creator": m.get("creator"), "externalIds": m.get("externalIds") or {}}, cal, rows
            )
            counts.setdefault(t, Counter())["ok" if b and b.file() else "none"] += 1
            if not (b and b.file()):
                lines["none"].append(f"{m['title']} (book)")
            continue
        if t not in ("TV Series", "Movie"):
            continue
        start = str((m.get("details") or {}).get("start") or "")
        year = int(start[:4]) if start[:4].isdigit() else None
        ms = match_video({"title": m["title"], "type": t, "year": year}, folders, index)
        best, why = best_video(ms)
        counts.setdefault(t, Counter())[why] += 1
        if why == "none":
            lines["none"].append(f"{m['title']} ({t}, {year or '?'})")
        elif why != "ok":
            lines["check"].append(f"{m['title']} ({year or '?'}): {why}: " + ", ".join(x.folder.path for x in ms[:3]))
    out = [
        f"{len(folders)} work folders on the disk; Calibre {'read' if cal else 'not found'}.",
        "",
        "| type | ok | check | not on the disk |",
        "|---|---|---|---|",
    ]
    for t, c in sorted(counts.items()):
        out.append(f"| {t} | {c['ok']} | {c['ambiguous'] + c['year']} | {c['none']} |")
    if lines["check"]:
        out += ["", "Needs a look:"] + [f"- {x}" for x in lines["check"]]
    if lines["none"]:
        out += ["", "Not on the disk:"] + [f"- {x}" for x in lines["none"]]
    return "\n".join(out)
