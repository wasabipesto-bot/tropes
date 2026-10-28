"""The matching pipeline, as functions: dossiers, pass 1, pass 2, check a subject, evidence,
the writing check. Jobs and the eval command call these; they do not talk to the site."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLM, load_prompt
from .schemas import CheckOut, DossierOut, EvidenceOut, Pass1Out, Pass2Out, RewriteOut
from .settings import Settings
from .sources import CHARS_PER_TOKEN, Text, blocks_for, find_quote, from_chapters, load_text, text_blocks, text_section
from .writing_check import complaints

log = logging.getLogger("tropes_worker.pipeline")


def subject_key(kind: str, sid: int) -> str:
    return f"{kind}:{sid}"


def entry_text(subject: dict[str, Any]) -> str:
    """The log entry as the prompts see it."""
    if subject["kind"] == "series":
        return f"Series: {subject['name']}\n{subject.get('description') or ''}".strip()
    parts = [f"Title: {subject['title']}", f"Type: {subject.get('label') or subject.get('type')}"]
    if subject.get("creator"):
        parts.append(f"Creator: {subject['creator']}")
    if subject.get("year"):
        parts.append(f"Logged: {subject['year']}")
    if subject.get("description"):
        parts.append(f"Owner's description: {subject['description']}")
    return "\n".join(parts)


MAX_VIDEO_WORDS = 60_000


def ensure_texts(client: Any, settings: Settings, subjects: list[dict[str, Any]]) -> int:
    """Pull the texts the media worker extracted (Phase 5) into the local cache and list them as text sources,
    one file per work in episode order, so the rest of the pipeline reads them like a linked EPUB. Returns fetched."""
    fetched = 0
    cache = settings.text_cache_dir / "site"
    for m in subjects:
        if m.get("kind") != "media":
            continue
        rows = [s for s in (m.get("localSources") or []) if s.get("indexedAt") and (s.get("meta") or {}).get("textHash")]
        # A video file whose "subtitles" run to more than 60k words is typesetting residue, not dialogue; it stays out.
        bloated = [s for s in rows if s.get("kind") == "video" and int((s.get("meta") or {}).get("words") or 0) > MAX_VIDEO_WORDS]
        if bloated:
            log.warning(
                "%s: %d subtitle text(s) over %d words skipped (typesetting residue)",
                m.get("title"),
                len(bloated),
                MAX_VIDEO_WORDS,
            )
            rows = [s for s in rows if s not in bloated]
        if not rows:
            continue
        rows.sort(key=lambda s: (s.get("label") or "", s["id"]))
        combined = hashlib.sha1("|".join(f"{s['id']}:{s['meta']['textHash']}" for s in rows).encode()).hexdigest()[:16]
        target = cache / f"{m['id']}-{combined}.txt"
        if not target.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            parts = []
            for s in rows:
                text = client.source_text(s["id"])
                if text:
                    parts.append(text.strip())
                    fetched += 1
            if parts:
                target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
                for old in cache.glob(f"{m['id']}-*.txt"):
                    if old != target:
                        old.unlink(missing_ok=True)
        if target.is_file():
            m["textSources"] = [str(target)] + [p for p in (m.get("textSources") or []) if p != str(target)]
    return fetched


def load_subject_text(settings: Settings, subject: dict[str, Any], texts_by_media: dict[int, Text] | None = None) -> Text | None:
    """The work's text when a source is linked; for a series, the members' texts concatenated."""
    if subject["kind"] == "media":
        paths = subject.get("textSources") or []
        if not paths:
            return None
        p = Path(paths[0])
        if not p.is_absolute():
            p = settings.sources_dir / p
        if not p.is_file():
            log.warning("text source missing for %s: %s", subject.get("title"), p)
            return None
        return load_text(p, settings.text_cache_dir)
    if texts_by_media:
        members = [texts_by_media[m] for m in subject.get("members", []) if m in texts_by_media]
        if members:
            full = "\n\n".join(t.full for t in members)
            chapters = [c for t in members for c in t.chapters]
            return Text(path=Path("series"), source_hash="+".join(t.source_hash for t in members), full=full, chapters=chapters)
    return None


# Dossiers -----------------------------------------------------------------


def extract_hash(subject: dict[str, Any]) -> str | None:
    """Source hash for a knowledge dossier built with the Wikipedia extract, so a changed extract rebuilds it."""
    text = subject.get("wikiExtract")
    return "wiki:" + hashlib.sha1(text.encode()).hexdigest() if text else None


def wants_extract(subject: dict[str, Any]) -> bool:
    """The extract feeds dossiers the model knows only partly or not at all (plan D16); strong ones do without."""
    d = subject.get("dossier")
    return bool(subject.get("wikiExtract")) and (not d or d.get("known") in ("partial", "none"))


def dossier_needed(subject: dict[str, Any], prompt_version: int, has_text: bool, source_hash: str | None) -> bool:
    d = subject.get("dossier")
    if not d:
        return True
    if d["promptVersion"] < prompt_version:
        return True
    if has_text and d["depth"] != "text":
        return True
    if has_text and d.get("sourceHash") != source_hash:
        return True
    if not has_text and wants_extract(subject) and d.get("sourceHash") != extract_hash(subject):
        return True
    return False


def text_input(text: Text | None) -> dict[str, Any] | None:
    """What the dossier page says about the text that was read: size and the span of its headings."""
    if text is None:
        return None
    heads = [t for t, _ in text.chapters if t != "Front matter"]
    return {
        "words": text.words,
        "chapters": len(text.chapters),
        "from": heads[0] if heads else None,
        "to": heads[-1] if len(heads) > 1 else None,
        "file": text.path.name,
    }


def visual_section(notes: list[dict[str, Any]], cap: int = 60_000) -> str:
    """The model's notes from the contact sheets (plan T11), one block per episode in order, within a character cap."""
    rows = sorted((n for n in notes if n.get("source") == "visual"), key=lambda n: n.get("label") or "")
    if not rows:
        return ""
    parts = []
    used = 0
    for n in rows:
        block = f"{n.get('label') or 'Whole work'}:\n{n['text']}"
        if used + len(block) > cap:
            parts.append("(further episodes omitted)")
            break
        parts.append(block)
        used += len(block)
    return "Visual notes, taken from frames of the actual footage (what is shown, not said):\n" + "\n\n".join(parts)


def wiki_section(notes: list[dict[str, Any]], cap: int = 40_000) -> str:
    """Fandom article summaries fetched for the work (plan T12)."""
    rows = [n for n in notes if n.get("source") == "wiki"]
    if not rows:
        return ""
    body = "\n\n".join(f"{n.get('label') or 'Summary'}:\n{n['text']}" for n in rows)
    return "Fan wiki summary (may contain errors; prefer the text when they disagree):\n" + body[:cap]


def cap_chars(settings: Settings) -> int:
    return settings.text_cap_tokens * CHARS_PER_TOKEN


async def build_dossier(
    llm: LLM, settings: Settings, subject: dict[str, Any], text: Text | None, notes: list[dict[str, Any]]
) -> dict[str, Any]:
    """One dossier for a work; a text over the cap (plan D7) gets one per block, merged like a series."""
    if text is not None and len(text.full) > cap_chars(settings):
        blocks = text_blocks(text, cap_chars(settings) // 2)
        parts = await llm.gather([build_dossier_once(llm, settings, subject, b, notes) for b in blocks])
        out = await llm.complete(
            "series_dossier",
            {
                "name": subject.get("title") or subject.get("name") or "",
                "description": f"One long work read in {len(blocks)} consecutive blocks of episodes; the parts below are those blocks in order.",  # noqa: E501
                "members": [p["body"] for p in parts],
            },
            DossierOut,
            model=settings.model_dossier,
        )
        merged = dict(parts[0])
        merged["body"] = out.model_dump()
        merged["sourceHash"] = text.source_hash
        merged["inputs"] = {**parts[0]["inputs"], "text": text_input(text), "blocks": len(blocks)}
        return merged
    return await build_dossier_once(llm, settings, subject, text, notes)


async def build_dossier_once(
    llm: LLM, settings: Settings, subject: dict[str, Any], text: Text | None, notes: list[dict[str, Any]]
) -> dict[str, Any]:
    owner = [n for n in notes if n.get("source") not in ("visual", "wiki")]
    notes_block = "\n\n".join(f"- {n['text'][:2000]}" for n in owner) or "(none)"
    use_extract = text is None and wants_extract(subject)
    extract = f"Encyclopaedia summary:\n{subject['wikiExtract']}" if use_extract else ""
    out = await llm.complete(
        "dossier",
        {
            "entry": entry_text(subject),
            "notes": notes_block,
            "extract": extract,
            "visual": visual_section(notes),
            "wiki": wiki_section(notes),
            "text_section": text_section(text),
        },
        DossierOut,
        model=settings.model_dossier,
    )
    return {
        "subject": {"kind": subject["kind"], "id": subject["id"]},
        "depth": "text" if text else "knowledge",
        "body": out.model_dump(),
        "model": settings.model_dossier,
        "promptVersion": load_prompt("dossier").version,
        "sourceHash": text.source_hash if text else (extract_hash(subject) if use_extract else None),
        "inputs": {
            "text": text_input(text),
            "posts": len(owner),
            "visual": sum(1 for n in notes if n.get("source") == "visual"),
            "wiki": next((n.get("url") or True for n in notes if n.get("source") == "wiki"), None),
            "extract": use_extract,
        },
    }


async def build_series_dossier(
    llm: LLM, settings: Settings, series: dict[str, Any], member_dossiers: list[dict[str, Any]]
) -> dict[str, Any]:
    out = await llm.complete(
        "series_dossier",
        {"name": series["name"], "description": series.get("description") or "", "members": member_dossiers},
        DossierOut,
        model=settings.model_dossier,
    )
    return {
        "subject": {"kind": "series", "id": series["id"]},
        "depth": "knowledge",
        "body": out.model_dump(),
        "model": settings.model_dossier,
        "promptVersion": load_prompt("series_dossier").version,
        "sourceHash": None,
    }


# Scanning a trope ---------------------------------------------------------


@dataclass
class TropeSpec:
    id: int | None
    name: str
    description: str
    seeds: list[str]
    seed_subjects: set[str] = field(default_factory=set)
    existing: dict[str, dict[str, Any]] = field(default_factory=dict)  # subject key -> instance
    rejected: set[str] = field(default_factory=set)
    # title -> (who, text) for seeds that already have an entry, so pass 2 sees the bar concretely.
    seed_entries: dict[str, tuple[str, str]] = field(default_factory=dict)

    def seeds_block(self) -> str:
        if not self.seeds:
            return "(none given)"
        lines = []
        for title in self.seeds:
            who, text = self.seed_entries.get(title, ("", ""))
            lines.append(f"- {title}: {who}. {text}".rstrip(". ") + "." if text else f"- {title}")
        return "\n".join(lines)


@dataclass
class Candidate:
    subject: dict[str, Any]
    score1: float
    reason: str
    seed: bool
    rejected_before: bool


def dossier_block(dossiers: dict[str, dict[str, Any]], key: str) -> str:
    d = dossiers.get(key)
    if not d:
        return "(no dossier)"
    return json.dumps(d["body"], ensure_ascii=False)


async def pass1(
    llm: LLM,
    settings: Settings,
    trope: TropeSpec,
    subjects: list[dict[str, Any]],
    dossiers: dict[str, dict[str, Any]],
    progress=None,
) -> dict[str, tuple[float, str]]:
    """Score every subject. Returns key -> (score, reason)."""
    batches = [subjects[i : i + settings.pass1_batch] for i in range(0, len(subjects), settings.pass1_batch)]
    scores: dict[str, tuple[float, str]] = {}
    done = 0

    async def one(batch: list[dict[str, Any]]) -> None:
        nonlocal done
        listing = "\n\n".join(
            f"subject {subject_key(s['kind'], s['id'])}\n{entry_text(s)}\nDossier: {dossier_block(dossiers, subject_key(s['kind'], s['id']))}"  # noqa: E501
            for s in batch
        )
        out = await llm.complete(
            "pass1",
            {"trope_name": trope.name, "trope_description": trope.description, "seeds": trope.seeds_block(), "batch": listing},
            Pass1Out,
        )
        for item in out.items:
            scores[item.subject.strip()] = (item.score, item.reason)
        done += len(batch)
        if progress:
            progress(done, len(subjects), "pass 1")

    await llm.gather([one(b) for b in batches])
    for s in subjects:
        scores.setdefault(subject_key(s["kind"], s["id"]), (0.0, "not scored"))
    return scores


def choose_candidates(
    settings: Settings, trope: TropeSpec, subjects: list[dict[str, Any]], scores: dict[str, tuple[float, str]]
) -> list[Candidate]:
    cands: list[Candidate] = []
    for s in subjects:
        key = subject_key(s["kind"], s["id"])
        if key in trope.existing:
            continue
        score, reason = scores.get(key, (0.0, ""))
        seed = key in trope.seed_subjects
        if seed or score >= settings.pass2_min_score:
            cands.append(Candidate(subject=s, score1=score, reason=reason, seed=seed, rejected_before=key in trope.rejected))
    cands.sort(key=lambda c: (not c.seed, -c.score1))
    seeds = [c for c in cands if c.seed]
    rest = [c for c in cands if not c.seed][: max(0, settings.pass2_cap - len(seeds))]
    return seeds + rest


STAMP_LINE_RX = re.compile(r"^\[(\d+:\d{2}(?::\d{2})?)\] ", re.M)


def quote_stamp(text: Text, chapter: str, content: str) -> tuple[str, float] | None:
    """For subtitle text, the `[12:40]` stamp of the line a quote starts on: ("12:40", 760.0)."""
    body = next((b for t, b in text.chapters if t == chapter), None)
    if body is None or "[" not in body[:40]:
        return None
    from .media.subtitles import parse_stamp

    needle = _norm_quote(content)[:60]
    for line in body.splitlines():
        m = STAMP_LINE_RX.match(line)
        if m and needle and needle in _norm_quote(line):
            secs = parse_stamp(m.group(1))
            if secs is not None:
                return m.group(1), secs
    return None


def _norm_quote(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quotes(text: Text | None, quotes: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """Keep only quotes found verbatim; return (kept, dropped). Quotes from subtitle text carry the episode
    label and timestamp in the locator ("S01E03 12:40") and the seconds in `at`, so a frame can be grabbed."""
    if text is None:
        return [], len(quotes)
    kept = []
    dropped = 0
    for q in quotes:
        found, chapter = find_quote(text, q.content)
        if not found:
            dropped += 1
            continue
        stamped = quote_stamp(text, chapter, q.content) if chapter else None
        if stamped:
            label = (chapter or "").split(" ")[0] if re.match(r"^S\d+E\d+", chapter or "") else ""
            item: dict[str, Any] = {
                "kind": "quote",
                "content": q.content.strip(),
                "locator": f"{label} {stamped[0]}".strip(),
                "at": stamped[1],
            }
            kept.append(item)
            continue
        locator = q.locator or chapter or ""
        if chapter and chapter.lower() not in locator.lower():
            locator = f"{chapter}" if not locator else f"{chapter}, {locator}"
        kept.append({"kind": "quote", "content": q.content.strip(), "locator": locator})
    return kept, dropped


async def polish(llm: LLM, text: str) -> tuple[str, list[str]]:
    """Run the writing check; one rewrite on a trip; flag if it still trips."""
    issues = complaints(text)
    if not issues or text.strip() == "":
        return text, []
    out = await llm.complete("rewrite", {"complaints": "\n".join(f"- {c}" for c in issues), "text": text}, RewriteOut)
    again = complaints(out.text)
    return out.text, ([f"writing check: {', '.join(again)}"] if again else [])


def text_for_pass2(settings: Settings, text: Text | None, reason: str, dossier: dict[str, Any] | None) -> Text | None:
    """Plan D7: a text over the cap is read in the block the pass-1 reason names (S01E03 labels or chapter
    headings) plus the next one; failing that, the blocks the dossier's scene locators point at."""
    if text is None or len(text.full) <= cap_chars(settings):
        return text
    blocks = text_blocks(text, cap_chars(settings) // 2)
    chosen = blocks_for(blocks, reason)
    if chosen == blocks[:1] and dossier:
        locs = " ".join(str(x.get("locator") or "") for x in (dossier.get("body") or {}).get("notable_scenes", []))
        chosen = blocks_for(blocks, locs)
    chapters = [c for b in chosen for c in b.chapters]
    return from_chapters(text, chapters, ", ".join(b.path.stem for b in chosen))


async def pass2(
    llm: LLM, settings: Settings, trope: TropeSpec, cand: Candidate, dossiers: dict[str, dict[str, Any]], text: Text | None
) -> dict[str, Any] | None:
    s = cand.subject
    key = subject_key(s["kind"], s["id"])
    text = text_for_pass2(settings, text, cand.reason, dossiers.get(key))
    out = await llm.complete(
        "pass2",
        {
            "trope_name": trope.name,
            "trope_description": trope.description,
            "seeds": trope.seeds_block(),
            "entry": entry_text(s),
            "dossier": dossier_block(dossiers, key),
            "text_section": text_section(text),
        },
        Pass2Out,
    )
    if not out.match and not cand.seed:
        return None
    flags: list[str] = []
    text_out, text_flags = await polish(llm, out.text)
    flags += text_flags
    evidence, dropped = verify_quotes(text, out.evidence)
    if dropped:
        flags.append(f"{dropped} quote{'s' if dropped > 1 else ''} not found in the text and dropped")
    if cand.seed and not out.match:
        flags.append("the model did not find the trope in this seed example")
    return {
        "tropeId": trope.id,
        "subject": {"kind": s["kind"], "id": s["id"]},
        "kind": "instance",
        "score": out.score,
        "prominence": out.prominence,
        "who": out.who.strip(),
        "text": text_out.strip(),
        "evidence": evidence,
        "seed": cand.seed,
        "rejectedBefore": cand.rejected_before,
        "flags": flags,
    }


async def new_evidence(
    llm: LLM, trope: TropeSpec, inst: dict[str, Any], existing_quotes: list[str], text: Text
) -> list[dict[str, str]]:
    out = await llm.complete(
        "evidence",
        {
            "trope_name": trope.name,
            "trope_description": trope.description,
            "who": inst.get("who") or "",
            "text": inst.get("text") or "",
            "existing": "\n".join(f"- {q[:200]}" for q in existing_quotes) or "(none)",
            "text_section": text_section(text),
        },
        EvidenceOut,
    )
    kept, _ = verify_quotes(text, out.evidence)
    return kept


# Checking one subject against all tropes ----------------------------------


async def check_subject(
    llm: LLM,
    settings: Settings,
    subject: dict[str, Any],
    dossiers: dict[str, dict[str, Any]],
    tropes: list[dict[str, Any]],
    text: Text | None,
    existing_trope_ids: set[int],
) -> list[dict[str, Any]]:
    listing = "\n\n".join(
        f"trope_id {t['id']}: {t['name']}\n{t['description']}\nOwner's examples: {', '.join(s['title'] for s in t.get('seeds', [])) or '(none)'}"  # noqa: E501
        for t in tropes
        if t["id"] not in existing_trope_ids
    )
    if not listing:
        return []
    key = subject_key(subject["kind"], subject["id"])
    if text is not None and len(text.full) > cap_chars(settings):
        text = text_blocks(text, cap_chars(settings))[0]
    out = await llm.complete(
        "check_subject",
        {
            "entry": entry_text(subject),
            "dossier": dossier_block(dossiers, key),
            "text_section": text_section(text),
            "tropes": listing,
        },
        CheckOut,
    )
    proposals = []
    for item in out.items:
        if not item.match or item.trope_id in existing_trope_ids:
            continue
        flags: list[str] = []
        text_out, text_flags = await polish(llm, item.text)
        flags += text_flags
        evidence, dropped = verify_quotes(text, item.evidence)
        if dropped:
            flags.append(f"{dropped} quote{'s' if dropped > 1 else ''} not found in the text and dropped")
        proposals.append(
            {
                "tropeId": item.trope_id,
                "subject": {"kind": subject["kind"], "id": subject["id"]},
                "kind": "instance",
                "score": item.score,
                "prominence": item.prominence,
                "who": item.who.strip(),
                "text": text_out.strip(),
                "evidence": evidence,
                "seed": False,
                "rejectedBefore": False,
                "flags": flags,
            }
        )
    proposals.sort(key=lambda p: -p["score"])
    return proposals


def run_async(coro):  # noqa: ANN001
    """Run a job coroutine in its own loop, closing the model clients it opened before the loop goes away."""

    async def wrapped():  # noqa: ANN202
        try:
            return await coro
        finally:
            await LLM.close_all()

    return asyncio.run(wrapped())
