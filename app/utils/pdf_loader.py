"""
app/utils/pdf_loader.py

Extracts clean text from typed (non-scanned) PDF documents using PyMuPDF.

Public API:
  extract_text_from_pdf(path)  -> str
  extract_pages(path)          -> List[dict]  (page-level, for debugging)
"""

import logging
import re
from pathlib import Path
from typing import List

import fitz  # PyMuPDF — import name is 'fitz'

logger = logging.getLogger(__name__)


# ── Main extraction function ─────────────────────────────────────────────────

def extract_text_from_pdf(path: str) -> str:
    """
    Extract all text from a typed PDF as a single cleaned string.

    Strategy:
      - Reads every page in order
      - Joins page text with a page-break marker
      - Applies text cleanup (removes ligature artifacts, normalises whitespace)

    Args:
        path: Absolute or relative path to the .pdf file.

    Returns:
        Clean text string. Raises ValueError if extraction yields nothing.

    Raises:
        FileNotFoundError : PDF file does not exist at path.
        ValueError        : PDF appears to be scanned / image-only.
        RuntimeError      : PyMuPDF could not open the file.
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    logger.info("[pdf_loader] Opening %s", pdf_path.name)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f"PyMuPDF could not open '{path}': {exc}") from exc

    pages_text: List[str] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")   # "text" mode = plain text, layout-aware
        if text.strip():
            pages_text.append(text)

    doc.close()

    if not pages_text:
        raise ValueError(
            f"No extractable text found in '{pdf_path.name}'. "
            "This tool only supports typed (non-scanned) PDFs."
        )

    # Join pages with a clear separator so chunking can respect page breaks
    raw = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
    cleaned = _clean_text(raw)

    logger.info(
        "[pdf_loader] Extracted %d pages, %d chars from %s",
        len(pages_text), len(cleaned), pdf_path.name,
    )
    return cleaned


def extract_pages(path: str) -> List[dict]:
    """
    Extract text page-by-page. Useful for debugging or page-level filtering.

    Returns:
        List of {"page": int, "text": str, "char_count": int}
    """
    pdf_path = Path(path)
    doc = fitz.open(str(pdf_path))
    pages = []

    for i in range(len(doc)):
        page = doc.load_page(i)
        text = _clean_text(page.get_text("text"))
        pages.append({
            "page":       i + 1,
            "text":       text,
            "char_count": len(text),
        })

    doc.close()
    return pages


# ── Text cleanup ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """
    Normalises raw PDF text:
      - Replaces common ligature artifacts (ﬁ ﬂ etc.)
      - Collapses excessive whitespace / blank lines
      - Strips trailing spaces from each line
      - Removes null bytes / control characters
    """
    # Ligature map
    ligatures = {
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb00": "ff",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u00a0": " ",   # non-breaking space
    }
    for char, replacement in ligatures.items():
        text = text.replace(char, replacement)

    # Remove control characters except newlines and tabs
    text = re.sub(r"[^\S\n\t ]+", " ", text)

    # Collapse 3+ consecutive blank lines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    text  = "\n".join(lines).strip()

    return text