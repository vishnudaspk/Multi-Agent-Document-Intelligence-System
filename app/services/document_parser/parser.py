"""
app/services/document_parser/parser.py

Parses documents using unstructured.io (primary) with pypdf as fallback.

Strategy tiers:
  1. unstructured  strategy="fast"  — no poppler/tesseract required
  2. pypdf                          — pure-Python PDF fallback (no C deps)

"hi_res" was removed: it requires poppler + tesseract and triggers
a broken docling/transformers import (AutoModelForImageTextToText).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.core.logging import logger


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page_number: Optional[int] = None
    element_type: str = "text"
    section: Optional[str] = None
    meta: dict = field(default_factory=dict)


SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".txt", ".md", ".html", ".htm",
    ".png", ".jpg", ".jpeg",
}


# ── Tier 1: unstructured (fast — no poppler/tesseract) ───────────────────────

def parse_with_unstructured(file_path: str, filename: str) -> List[TextChunk]:
    """
    Primary parser — uses unstructured.io with strategy='fast'.
    'fast' uses pdfminer internally for PDFs (pure Python, no poppler).
    Semantic chunking via chunk_by_title.
    """
    from unstructured.partition.auto import partition
    from unstructured.chunking.title import chunk_by_title

    logger.info("parser.unstructured.start", path=file_path)

    elements = partition(filename=file_path, strategy="fast")

    chunks_elements = chunk_by_title(
        elements,
        max_characters=1000,
        new_after_n_chars=800,
        overlap=100,
    )

    raw_chunks: List[TextChunk] = []
    for idx, el in enumerate(chunks_elements):
        text = str(el).strip()
        if not text:
            continue

        el_type = type(el).__name__.lower()
        metadata = el.metadata
        page = getattr(metadata, "page_number", None)
        section = getattr(metadata, "section", None)

        raw_chunks.append(TextChunk(
            text=text,
            chunk_index=idx,
            page_number=page,
            element_type=el_type,
            section=section,
            meta={"source": filename, "parser": "unstructured"},
        ))

    logger.info("parser.unstructured.done", chunks=len(raw_chunks))
    return raw_chunks


# ── Tier 2: pypdf (pure-Python PDF fallback) ─────────────────────────────────

def parse_with_pypdf(file_path: str, filename: str) -> List[TextChunk]:
    """
    Fallback parser — uses pypdf (pure Python, zero C dependencies).
    Splits extracted text into ~800-char semantic chunks.
    Works for any text-based PDF without poppler or tesseract.
    """
    import pypdf

    logger.info("parser.pypdf.start", path=file_path)

    reader = pypdf.PdfReader(file_path)
    chunks: List[TextChunk] = []
    chunk_index = 0

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if not page_text:
            continue

        # Split on paragraph breaks first, then re-aggregate into ~800-char chunks
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", page_text) if p.strip()]
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > 800 and current:
                chunks.append(TextChunk(
                    text=current.strip(),
                    chunk_index=chunk_index,
                    page_number=page_num,
                    element_type="text",
                    meta={"source": filename, "parser": "pypdf"},
                ))
                chunk_index += 1
                current = para
            else:
                current = (current + "\n\n" + para).strip()

        if current:
            chunks.append(TextChunk(
                text=current.strip(),
                chunk_index=chunk_index,
                page_number=page_num,
                element_type="text",
                meta={"source": filename, "parser": "pypdf"},
            ))
            chunk_index += 1

    logger.info("parser.pypdf.done", chunks=len(chunks))
    return chunks


# ── Tier 3: plain-text fallback (txt, md, html) ──────────────────────────────

def parse_plain_text(file_path: str, filename: str) -> List[TextChunk]:
    """Simple line-based chunker for .txt / .md / .html files."""
    logger.info("parser.plaintext.start", path=file_path)
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks: List[TextChunk] = []
    current = ""
    idx = 0
    for para in paragraphs:
        if len(current) + len(para) > 800 and current:
            chunks.append(TextChunk(
                text=current.strip(), chunk_index=idx,
                meta={"source": filename, "parser": "plaintext"},
            ))
            idx += 1
            current = para
        else:
            current = (current + "\n\n" + para).strip()
    if current:
        chunks.append(TextChunk(
            text=current.strip(), chunk_index=idx,
            meta={"source": filename, "parser": "plaintext"},
        ))

    logger.info("parser.plaintext.done", chunks=len(chunks))
    return chunks


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_document(file_path: str, filename: str) -> List[TextChunk]:
    """
    Main entry point.
    Tier 1 → unstructured (fast)
    Tier 2 → pypdf          (PDF-only fallback)
    Tier 3 → plain text     (.txt/.md/.html)
    Raises ValueError for unsupported file types.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    # Tier 1 — unstructured
    try:
        chunks = parse_with_unstructured(file_path, filename)
        if chunks:
            return chunks
        logger.warning("parser.unstructured.empty_result", path=file_path)
    except Exception as e:
        logger.warning("parser.unstructured.failed", error=str(e), path=file_path)

    # Tier 2 — pypdf (PDF only)
    if ext == ".pdf":
        try:
            chunks = parse_with_pypdf(file_path, filename)
            if chunks:
                return chunks
            logger.warning("parser.pypdf.empty_result", path=file_path)
        except Exception as e:
            logger.warning("parser.pypdf.failed", error=str(e), path=file_path)

    # Tier 3 — plain text
    if ext in {".txt", ".md", ".html", ".htm"}:
        return parse_plain_text(file_path, filename)

    raise ValueError(
        f"All parsers failed for {filename}. "
        "For scanned PDFs, install poppler and tesseract and use strategy='hi_res'."
    )
