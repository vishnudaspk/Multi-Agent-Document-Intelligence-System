"""
tests/unit/test_parser.py — unit tests for the document parser.
"""
import tempfile
from pathlib import Path

import pytest

from app.services.document_parser.parser import TextChunk, parse_document


def test_text_chunk_dataclass():
    """TextChunk fields should have sensible defaults."""
    chunk = TextChunk(text="hello", chunk_index=0)
    assert chunk.element_type == "text"
    assert chunk.meta == {}
    assert chunk.page_number is None
    assert chunk.section is None


def test_text_chunk_with_metadata():
    chunk = TextChunk(
        text="content", chunk_index=1,
        page_number=3, element_type="narrative",
        section="Introduction", meta={"key": "val"},
    )
    assert chunk.page_number == 3
    assert chunk.meta["key"] == "val"


def test_parse_document_txt():
    """parse_document should handle plain .txt files."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("The Eiffel Tower was completed in 1889. " * 20)
        f.flush()
        path = f.name

    chunks = parse_document(path, "test.txt")
    assert len(chunks) >= 1
    assert all(isinstance(c, TextChunk) for c in chunks)
    assert any("Eiffel" in c.text for c in chunks)

    Path(path).unlink(missing_ok=True)


def test_parse_document_empty_txt():
    """An empty .txt file should return an empty list, not crash."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("")
        f.flush()
        path = f.name

    chunks = parse_document(path, "empty.txt")
    assert isinstance(chunks, list)
    assert len(chunks) == 0

    Path(path).unlink(missing_ok=True)


def test_parse_document_md():
    """Markdown files should be parsed as plain text."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# Heading\n\nThis is a markdown document.\n\n## Section 2\n\nMore text here.")
        f.flush()
        path = f.name

    chunks = parse_document(path, "readme.md")
    assert len(chunks) >= 1
    assert any("markdown" in c.text.lower() for c in chunks)

    Path(path).unlink(missing_ok=True)


def test_parse_document_nonexistent_file():
    """Non-existent file should raise ValueError (all parsers fail)."""
    with pytest.raises(ValueError, match="All parsers failed"):
        parse_document("/nonexistent/path/file.pdf", "ghost.pdf")
