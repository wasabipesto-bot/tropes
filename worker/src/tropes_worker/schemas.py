"""Pydantic models for every prompt's output. Mirrors web/src/lib/jobs/schemas.ts where shapes cross the wire."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Prominence = Literal["core", "recurring", "brief"]


class Character(BaseModel):
    name: str
    role: str = ""
    descriptors: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class Located(BaseModel):
    summary: str
    locator: str | None = None


class DossierOut(BaseModel):
    known: Literal["strong", "partial", "none"]
    summary: str
    characters: list[Character] = Field(default_factory=list)
    settings: list[str] = Field(default_factory=list)
    arcs: list[Located] = Field(default_factory=list)
    motifs: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    notable_scenes: list[Located] = Field(default_factory=list)


class Pass1Item(BaseModel):
    subject: str
    score: float = Field(ge=0, le=1)
    reason: str = ""


class Pass1Out(BaseModel):
    items: list[Pass1Item]


class QuoteOut(BaseModel):
    content: str
    locator: str = ""


class Pass2Out(BaseModel):
    match: bool
    score: float = Field(ge=0, le=1)
    prominence: Prominence = "brief"
    who: str = ""
    text: str = ""
    evidence: list[QuoteOut] = Field(default_factory=list)


class CheckItem(BaseModel):
    trope_id: int
    match: bool
    score: float = Field(ge=0, le=1)
    prominence: Prominence = "brief"
    who: str = ""
    text: str = ""
    evidence: list[QuoteOut] = Field(default_factory=list)


class CheckOut(BaseModel):
    items: list[CheckItem]


class EvidenceOut(BaseModel):
    evidence: list[QuoteOut] = Field(default_factory=list)


class RewriteOut(BaseModel):
    text: str


class NoteVerdict(BaseModel):
    index: int
    about_the_work: bool


class NotesFilterOut(BaseModel):
    items: list[NoteVerdict]


class VisualNotesOut(BaseModel):
    notes: list[str] = []


class LookOut(BaseModel):
    seen: bool
    note: str = ""


class ResolveOut(BaseModel):
    choice: str | None = None
    confidence: float = Field(ge=0, le=1, default=0)
    why: str = ""


class GenresOut(BaseModel):
    genres: list[str] = Field(default_factory=list)
