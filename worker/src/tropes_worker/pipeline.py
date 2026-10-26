"""The matching pipeline, as functions: dossiers, pass 1, pass 2, check a subject, evidence,
the writing check. Jobs and the eval command call these; they do not talk to the site."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLM, load_prompt
from .schemas import CheckOut, DossierOut, EvidenceOut, Pass1Out, Pass2Out, RewriteOut
from .settings import Settings
from .sources import Text, find_quote, load_text, text_section
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


def ensure_texts(client: Any, settings: Settings, subjects: list[dict[str, Any]]) -> int:
    """Pull the texts the media worker extracted (Phase 5) into the local cache and list them as text sources,
    one file per work in episode order, so the rest of the pipeline reads them like a linked EPUB. Returns fetched."""
    fetched = 0
    cache = settings.text_cache_dir / "site"
    for m in subjects:
        if m.get("kind") != "media":
            continue
        rows = [s for s in (m.get("localSources") or []) if s.get("indexedAt") and (s.get("meta") or {}).get("textHash")]
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


async def build_dossier(
    llm: LLM, settings: Settings, subject: dict[str, Any], text: Text | None, notes: list[dict[str, Any]]
) -> dict[str, Any]:
    notes_block = "\n\n".join(f"- {n['text'][:2000]}" for n in notes) or "(none)"
    use_extract = text is None and wants_extract(subject)
    extract = f"Encyclopaedia summary:\n{subject['wikiExtract']}" if use_extract else ""
    out = await llm.complete(
        "dossier",
        {"entry": entry_text(subject), "notes": notes_block, "extract": extract, "text_section": text_section(text)},
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


def verify_quotes(text: Text | None, quotes: list[Any]) -> tuple[list[dict[str, str]], int]:
    """Keep only quotes found verbatim; return (kept, dropped)."""
    if text is None:
        return [], len(quotes)
    kept = []
    dropped = 0
    for q in quotes:
        found, chapter = find_quote(text, q.content)
        if not found:
            dropped += 1
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


async def pass2(
    llm: LLM, settings: Settings, trope: TropeSpec, cand: Candidate, dossiers: dict[str, dict[str, Any]], text: Text | None
) -> dict[str, Any] | None:
    s = cand.subject
    key = subject_key(s["kind"], s["id"])
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
