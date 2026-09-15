"""Extract raw (page, text) pairs from a source file. FR-1."""
from pathlib import Path
from typing import List, Tuple


def load_pages(file_path: str) -> List[Tuple[int, str]]:
    """Returns a list of (page_number, page_text). page_number starts at 1.
    TXT/MD files are returned as a single 'page'.
    """
    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        return _load_pdf(file_path)
    if suffix == ".docx":
        return _load_docx(file_path)
    if suffix in (".txt", ".md"):
        return _load_text(file_path)

    raise ValueError(f"Unsupported file type: {suffix}")


def _load_pdf(file_path: str) -> List[Tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def _load_docx(file_path: str) -> List[Tuple[int, str]]:
    import docx

    doc = docx.Document(file_path)
    # docx has no native page concept — treat whole doc as page 1,
    # section-level structure is recovered later by the chunker via heading styles.
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [(1, full_text)]


def _load_text(file_path: str) -> List[Tuple[int, str]]:
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return [(1, text)]
