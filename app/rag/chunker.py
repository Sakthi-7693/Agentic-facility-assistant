"""Document loading and chunking.

Splitting on markdown headings first keeps each chunk about one topic. The
heading trail is prepended to every chunk so it still makes sense on its own
after retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import KNOWLEDGE_BASE_DIR, settings
from app.logging_setup import get_logger

log = get_logger(__name__)

HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    id: str
    text: str
    source: str   # file name, shown as the citation
    section: str  # heading trail, e.g. "AHU Guide > Low Airflow"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def _split_by_heading(text: str) -> list[tuple[str, str]]:
    """Cut at every heading, tracking the trail of parent headings."""
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [("Document", text.strip())]

    trail: dict[int, str] = {}
    sections: list[tuple[str, str]] = []

    for position, match in enumerate(matches):
        level, title = len(match.group(1)), match.group(2).strip()

        trail[level] = title
        for deeper in [k for k in trail if k > level]:
            del trail[deeper]

        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()

        if body:
            sections.append((" > ".join(trail[k] for k in sorted(trail)), body))

    return sections


def _split_by_size(text: str) -> list[str]:
    """Break a long section into overlapping windows on paragraph boundaries."""
    size, overlap = settings.chunk_size, settings.chunk_overlap
    if len(text) <= size:
        return [text]

    pieces: list[str] = []
    buffer = ""

    for paragraph in text.split("\n\n"):
        if len(buffer) + len(paragraph) + 2 <= size:
            buffer = f"{buffer}\n\n{paragraph}".strip()
            continue
        if buffer:
            pieces.append(buffer)
        # Carry the tail forward so a sentence on the boundary stays findable.
        buffer = (buffer[-overlap:] + "\n\n" + paragraph).strip() if overlap else paragraph

    if buffer:
        pieces.append(buffer)
    return pieces


def split_document(name: str, text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    position = 0  # running counter keeps every chunk ID unique

    for section, body in _split_by_heading(text):
        for piece in _split_by_size(body):
            position += 1
            chunks.append(
                Chunk(
                    id=f"{name}#{position:03d}::{_slug(section)}",
                    text=f"[{name} | {section}]\n{piece}",
                    source=name,
                    section=section,
                )
            )
    return chunks


def load_documents(folder: Path = KNOWLEDGE_BASE_DIR) -> list[tuple[str, str]]:
    files = sorted(folder.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md documents found in {folder}")
    log.info("Loaded %d knowledge base documents", len(files))
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def build_chunks() -> list[Chunk]:
    chunks = [c for name, text in load_documents() for c in split_document(name, text)]
    log.info("Produced %d chunks", len(chunks))
    return chunks
