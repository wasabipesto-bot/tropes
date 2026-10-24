"""`tropes-worker lookup`: run identity resolution over a sample with no writes and print a report."""

from __future__ import annotations

import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..client import SiteClient
from ..settings import Settings
from .http import Fetcher
from .resolve import Entry, Resolution, resolve

HARD_CASES = [
    "Pantheon",
    "Dune",
    "Control",
    "Arcane",
    "Castlevania",
    "Good Omens",
    "Almost Nowhere",
    "Kerbal Space Prgram",
    "Harry Potter and the Goblet of Fire",
]


def entry_from(m: dict[str, Any]) -> Entry:
    return Entry(
        id=m["id"],
        title=m["title"],
        type=m["type"],
        creator=m.get("creator"),
        logged_year=m.get("year"),
        media_url=m.get("mediaUrl"),
    )


def shared_media_links(media: list[dict[str, Any]]) -> set[str]:
    counts = Counter(m.get("mediaUrl") for m in media if m.get("mediaUrl"))
    return {u for u, n in counts.items() if n > 1}


def pick_sample(media: list[dict[str, Any]], n: int, seed: int = 4) -> list[dict[str, Any]]:
    """n entries spread across types, plus the known hard cases when they are in the library."""
    rng = random.Random(seed)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for m in media:
        by_type.setdefault(m["type"], []).append(m)
    chosen = [m for m in media if m["title"] in HARD_CASES]
    ids = {m["id"] for m in chosen}
    per_type = max(1, (n - len(chosen)) // max(1, len(by_type)))
    for rows in by_type.values():
        for m in rng.sample(rows, min(per_type, len(rows))):
            if m["id"] not in ids:
                chosen.append(m)
                ids.add(m["id"])
    return chosen[:n] if len(chosen) > n else chosen


def run_sample(settings: Settings, client: SiteClient, *, sample: int | None, ids: list[int] | None, workers: int = 6) -> str:
    media = client.subjects()["media"]
    if ids:
        rows = [m for m in media if m["id"] in set(ids)]
    else:
        rows = pick_sample(media, sample or 50)
    shared = shared_media_links(media)
    f = Fetcher(cache_dir=settings.lookup_cache_dir, user_agent=settings.user_agent)
    started = time.monotonic()
    timings: dict[int, float] = {}

    def one(m: dict[str, Any]) -> tuple[dict[str, Any], Resolution]:
        t0 = time.monotonic()
        r = resolve(f, entry_from(m), shared_links=shared)
        timings[m["id"]] = time.monotonic() - t0
        return m, r

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, rows))
    elapsed = time.monotonic() - started
    f.close()
    return render(results, timings, elapsed, f.requests_made, f.cache_hits, f.warnings)


def render(
    results: list[tuple[dict[str, Any], Resolution]],
    timings: dict[int, float],
    elapsed: float,
    requests: int,
    hits: int,
    warnings: list[str],
) -> str:
    lines = ["| id | title | type | status | chosen | year | score | 2nd | why |", "|---|---|---|---|---|---|---|---|---|"]
    for m, r in sorted(results, key=lambda x: (x[0]["type"], x[0]["title"])):
        c = r.chosen
        second = f"{r.candidates[1].score:.2f}" if len(r.candidates) > 1 else ""
        why = "; ".join(c.reasons) if c else "; ".join(r.notes)
        chosen = f"{c.label} ({c.qid}) — {c.description[:50]}" if c else ""
        head = f"| {m['id']} | {m['title']} | {m['type']} | {r.status} |"
        lines.append(f"{head} {chosen} | {c.year} | {c.score:.2f} | {second} | {why} |" if c else f"{head} | | | | {why} |")
    by_status = Counter(r.status for _, r in results)
    by_type: dict[str, Counter] = {}
    for m, r in results:
        by_type.setdefault(m["type"], Counter())[r.status] += 1
    summary = [
        f"{len(results)} entries in {elapsed:.0f} s ({elapsed / max(1, len(results)):.1f} s each with 6 workers; "
        f"median {sorted(timings.values())[len(timings) // 2]:.1f} s per entry serial), {requests} requests, {hits} cache hits.",
        "",
        "| status | n |",
        "|---|---|",
    ] + [f"| {k} | {v} |" for k, v in by_status.most_common()]
    summary += ["", "| type | " + " | ".join(by_status) + " |", "|---|" + "---|" * len(by_status)]
    for t, c in sorted(by_type.items()):
        summary.append(f"| {t} | " + " | ".join(str(c.get(s, 0)) for s in by_status) + " |")
    if warnings:
        summary += ["", "Warnings: " + "; ".join(warnings)]
    return "\n".join(summary + ["", *lines])
