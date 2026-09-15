"""Chunk page text at a meaningful (section/clause) level, retaining page number. FR-4.

Strategy: split on clause-like headings ("4.2", "Section 4.2", "Clause 4.2", "Article 4.2")
where present; otherwise fall back to fixed-size paragraph chunks so nothing is dropped.
"""
import re
from dataclasses import dataclass
from typing import List, Tuple

CLAUSE_PATTERN = re.compile(
    r"^\s*((?:Section|Clause|Article)?\s*\d+(?:\.\d+)*[\.\)]?\s+.{0,80})",
    re.MULTILINE,
)

FALLBACK_CHUNK_CHARS = 1200
FALLBACK_OVERLAP_CHARS = 150


@dataclass
class RawChunk:
    text: str
    section_label: str | None
    page_number: int | None


def chunk_pages(pages: List[Tuple[int, str]]) -> List[RawChunk]:
    chunks: List[RawChunk] = []
    for page_number, page_text in pages:
        section_chunks = _split_by_clause(page_text)
        if section_chunks:
            for label, text in section_chunks:
                if text.strip():
                    chunks.append(RawChunk(text=text.strip(), section_label=label, page_number=page_number))
        else:
            for text in _split_fixed(page_text):
                chunks.append(RawChunk(text=text, section_label=None, page_number=page_number))
    return chunks


def _split_by_clause(text: str) -> List[Tuple[str, str]]:
    matches = list(CLAUSE_PATTERN.finditer(text))
    if not matches:
        return []

    results = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        label = m.group(1).strip()[:60]
        if block:
            results.append((label, block))
    return results


def _split_fixed(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + FALLBACK_CHUNK_CHARS, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - FALLBACK_OVERLAP_CHARS
    return [c for c in chunks if c]
