"""Text sources: turn a .txt or .epub into plain text with chapter markers, cached by file hash,
and find quotes in it so evidence can be checked verbatim."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

CHAPTER_MARK = "\n\n## "


@dataclass
class Text:
    path: Path
    source_hash: str
    full: str
    chapters: list[tuple[str, str]]  # (title, text)

    @property
    def words(self) -> int:
        return len(self.full.split())


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_gutenberg(text: str) -> str:
    start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I)
    end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK", text, re.I)
    if start:
        text = text[start.end() :]
    if end:
        text = (
            text[: end.start() - (start.end() if start and end.start() > start.end() else 0)]
            if False
            else text[: text.rfind("*** END OF")]
            if "*** END OF" in text
            else text
        )
    return text.strip()


def _txt_to_marked(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = _strip_gutenberg(text)
    # Our own web dumps already use "# Title" headings; turn them into chapter marks.
    text = re.sub(r"(?m)^# (.+)$", lambda m: f"{CHAPTER_MARK}{m.group(1).strip()}\n", text)
    # Common chapter headings in plain text.
    text = re.sub(
        r"(?mi)^((?:chapter|book|part|act|scene)\s+[\divxlc]+\.?[^\n]{0,80})$",
        lambda m: f"{CHAPTER_MARK}{m.group(1).strip()}\n",
        text,
    )
    return text.strip()


def _epub_to_marked(path: Path) -> str:
    import warnings

    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
    docs = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    order = [idref for idref, _ in book.spine if idref in docs] or list(docs)
    parts: list[str] = []
    for n, idref in enumerate(order, 1):
        soup = BeautifulSoup(docs[idref].get_content(), "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        heading = soup.find(["h1", "h2", "h3"])
        title = re.sub(r"\s+", " ", heading.get_text(" ")).strip() if heading else f"Section {n}"
        body = soup.get_text("\n")
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n\s*\n+", "\n\n", body).strip()
        if len(body.split()) < 20:
            continue
        parts.append(f"{CHAPTER_MARK}{title}\n{body}")
    return "\n".join(parts).strip()


def load_text(path: Path, cache_dir: Path) -> Text:
    """Plain text with `## Title` chapter marks, cached under cache_dir by content hash."""
    h = file_hash(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{h}.txt"
    if cached.is_file():
        marked = cached.read_text(encoding="utf-8")
    else:
        if path.suffix.lower() == ".epub":
            marked = _epub_to_marked(path)
        else:
            raw = path.read_bytes()
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                s = raw.decode("cp1252", errors="replace")
            marked = _txt_to_marked(s)
        cached.write_text(marked, encoding="utf-8")
    chapters: list[tuple[str, str]] = []
    pieces = re.split(r"\n\n## ", "\n\n" + marked) if marked.startswith("## ") else re.split(r"\n\n## ", marked)
    for i, piece in enumerate(pieces):
        piece = piece.strip()
        if not piece:
            continue
        if i == 0 and not marked.startswith("## "):
            chapters.append(("Front matter", piece))
            continue
        title, _, body = piece.partition("\n")
        chapters.append((title.strip(), body.strip()))
    return Text(path=path, source_hash=h, full=marked, chapters=chapters)


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def find_quote(text: Text, quote: str) -> tuple[bool, str | None]:
    """Is `quote` in the text verbatim (ignoring whitespace and quote style)? Returns (found, chapter title)."""
    q = _norm(quote)
    if len(q) < 12:
        return False, None
    for title, body in text.chapters:
        if q in _norm(body):
            return True, title
    return False, None


CHARS_PER_TOKEN = 4
SEASON_RX = re.compile(r"^S(\d{1,2})E\d{1,3}\b", re.I)


def text_section(text: Text | None, *, max_chars: int = 3_600_000) -> str:
    """The block a prompt gets when a source exists: the whole work, or nothing."""
    if text is None:
        return "No text of the work is available; rely on the dossier and your own knowledge, and return no evidence."
    body = text.full if len(text.full) <= max_chars else text.full[:max_chars] + "\n\n[text truncated]"
    if text.path.name.endswith("#block"):
        return f"Part of the work's text follows ({text.path.stem}), with `## ` chapter headings:\n\n{body}"
    return f"The full text of the work follows, with `## ` chapter headings:\n\n{body}"


def from_chapters(text: Text, chapters: list[tuple[str, str]], label: str) -> Text:
    """A Text made of some of another's chapters, so quotes verify against it the same way."""
    full = "\n\n".join(f"## {t}\n{b}" for t, b in chapters)
    return Text(path=Path(f"{label}#block"), source_hash=text.source_hash, full=full, chapters=chapters)


def text_blocks(text: Text, cap_chars: int) -> list[Text]:
    """Plan D7: a text over the cap split into consecutive blocks under it, breaking between seasons when the
    chapter headings carry S01E01 labels and between chapters otherwise. A text under the cap is one block."""
    if len(text.full) <= cap_chars or not text.chapters:
        return [text]
    groups: list[list[tuple[str, str]]] = []
    season: str | None = None
    for ch in text.chapters:
        m = SEASON_RX.match(ch[0])
        key = m.group(1) if m else None
        if groups and key is not None and key == season:
            groups[-1].append(ch)
        elif groups and key is None and season is None and sum(len(b) for _, b in groups[-1]) < cap_chars:
            groups[-1].append(ch)
        else:
            groups.append([ch])
            season = key
    # A season over the cap on its own is cut into runs of chapters.
    units: list[list[tuple[str, str]]] = []
    for g in groups:
        run: list[tuple[str, str]] = []
        size = 0
        for ch in g:
            if run and size + len(ch[1]) > cap_chars:
                units.append(run)
                run, size = [], 0
            run.append(ch)
            size += len(ch[1])
        if run:
            units.append(run)
    # Then consecutive units are packed while they fit.
    blocks: list[list[tuple[str, str]]] = []
    for u in units:
        if blocks and sum(len(b) for _, b in blocks[-1]) + sum(len(b) for _, b in u) <= cap_chars:
            blocks[-1].extend(u)
        else:
            blocks.append(list(u))
    out = []
    for i, chapters in enumerate(blocks, 1):
        label = f"block {i} of {len(blocks)}: {chapters[0][0]} to {chapters[-1][0]}"
        out.append(from_chapters(text, chapters, label))
    return out


def blocks_for(blocks: list[Text], mentions: str, limit: int = 2) -> list[Text]:
    """The blocks whose chapter headings (or S01E03 labels) appear in `mentions`, each with the next block, in
    order and up to `limit`; the first blocks when nothing is named. One block is returned unchanged."""
    if len(blocks) <= 1:
        return blocks
    low = mentions.lower()
    hit: set[int] = set()
    for i, b in enumerate(blocks):
        for title, _ in b.chapters:
            m = SEASON_RX.match(title)
            # "S01E03" or the episode's name after it; a bare chapter heading otherwise.
            labels = [m.group(0), title[m.end() :].strip(" :-")] if m else [title]
            if any(len(x) >= 6 and x.lower() in low for x in labels):
                hit.add(i)
                break
    if not hit:
        hit = {0}
    chosen: list[int] = []
    for i in sorted(hit):
        for j in (i, i + 1):
            if j < len(blocks) and j not in chosen:
                chosen.append(j)
    return [blocks[i] for i in sorted(chosen)[:limit]]
