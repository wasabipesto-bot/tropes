"""Genres from the controlled vocabulary (plan T5): the model maps each site's own genre strings onto it."""

from __future__ import annotations

from typing import Any

from ..llm import LLM
from ..schemas import GenresOut

KINDS_FOR = {"Album": {"music"}, "Game": {"story", "game"}, "Podcast": {"story", "podcast"}}


def applicable(vocab: dict[str, Any], type_: str) -> list[dict[str, Any]]:
    kinds = KINDS_FOR.get(type_, {"story"})
    return [g for g in vocab.get("genres", []) if g.get("kind") in kinds]


def vocabulary_block(entries: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {g['name']}" + (f" (subgenres: {', '.join(g['sub'])})" if g.get("sub") else "") for g in entries)


def clean(picked: list[str], entries: list[dict[str, Any]], limit: int = 4) -> list[str]:
    """Keep names from the vocabulary only; drop a parent when one of its subgenres is also chosen."""
    parent: dict[str, str] = {}
    for g in entries:
        parent[g["name"]] = g["name"]
        for s in g.get("sub", []):
            parent[s] = g["name"]
    valid = [p for p in dict.fromkeys(x.strip() for x in picked) if p in parent]
    subs_parents = {parent[p] for p in valid if parent[p] != p}
    return [p for p in valid if not (parent[p] == p and p in subs_parents)][:limit]


async def assign(
    llm: LLM, vocab: dict[str, Any], entry: str, type_: str, source_genres: list[str], extract: str | None
) -> list[str]:
    entries = applicable(vocab, type_)
    if not entries or (not source_genres and not extract):
        return []
    out = await llm.complete(
        "genres",
        {
            "entry": entry,
            "sources": ", ".join(source_genres) or "(none)",
            "extract": (extract or "(none)")[:1500],
            "vocabulary": vocabulary_block(entries),
        },
        GenresOut,
    )
    return clean(out.genres, entries)
