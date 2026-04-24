"""
app/utils/chunking.py

Splits extracted PDF text into overlapping chunks suitable for RAG.

Strategy: sentence-aware sliding window
  - Split on sentence boundaries first (not mid-word)
  - Build chunks by accumulating sentences up to chunk_size chars
  - Slide forward by (chunk_size - overlap) chars, keeping tail sentences
  - Respects page-break markers inserted by pdf_loader.py

Public API:
  chunk_text(text, chunk_size, overlap)       -> List[str]
  chunk_with_metadata(text, source, ...)      -> List[dict]
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# Sentence boundary pattern: end of sentence + whitespace
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Page break marker from pdf_loader
_PAGE_BREAK = "--- PAGE BREAK ---"


# ── Main chunking function ───────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """
    Split text into overlapping chunks, respecting sentence boundaries.

    Args:
        text       : Full document text (output of pdf_loader.extract_text_from_pdf).
        chunk_size : Target maximum characters per chunk (soft limit).
        overlap    : Characters of overlap between consecutive chunks.
                     Helps preserve context at chunk boundaries.

    Returns:
        List of non-empty text strings, each <= ~(chunk_size * 1.2) chars.

    Example:
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        # → ["Introduction. The report covers...", "The report covers Q3...", ...]
    """
    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be < chunk_size ({chunk_size})")

    # ── Split on page breaks first, then process each section ────
    sections = [s.strip() for s in text.split(_PAGE_BREAK) if s.strip()]
    all_chunks: List[str] = []

    for section in sections:
        all_chunks.extend(_chunk_section(section, chunk_size, overlap))

    logger.info(
        "[chunking] %d sections → %d chunks  (size=%d, overlap=%d)",
        len(sections), len(all_chunks), chunk_size, overlap,
    )
    return all_chunks


def chunk_with_metadata(
    text: str,
    source: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[dict]:
    """
    Same as chunk_text but returns dicts with metadata attached.
    Useful for debugging or custom upsert logic.

    Returns:
        List of {"content": str, "source": str, "chunk_index": int, "char_count": int}
    """
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    return [
        {
            "content":     c,
            "source":      source,
            "chunk_index": i,
            "char_count":  len(c),
        }
        for i, c in enumerate(chunks)
    ]


# ── Internal helpers ─────────────────────────────────────────────────────────

def _chunk_section(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Core sliding-window chunker for a single page-section.
    Splits into sentences, then greedily fills chunks.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: List[str] = []
    current_sentences: List[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If adding this sentence would exceed chunk_size AND we already have content
        if current_len + sentence_len > chunk_size and current_sentences:
            # Flush current chunk
            chunk = " ".join(current_sentences).strip()
            if chunk:
                chunks.append(chunk)

            # Build overlap: keep sentences from the tail until we have ~overlap chars
            overlap_sentences: List[str] = []
            overlap_len = 0
            for s in reversed(current_sentences):
                if overlap_len + len(s) > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_len += len(s)

            current_sentences = overlap_sentences
            current_len = overlap_len

        current_sentences.append(sentence)
        current_len += sentence_len

    # Flush remaining sentences
    if current_sentences:
        chunk = " ".join(current_sentences).strip()
        if chunk:
            chunks.append(chunk)

    return chunks


def _split_sentences(text: str) -> List[str]:
    """
    Split text into sentences using regex on punctuation boundaries.
    Falls back to splitting on double-newlines if text has no punctuation.
    """
    # First split on sentence-ending punctuation
    raw_sentences = _SENTENCE_END.split(text)

    # Further split on paragraph breaks (double newline)
    sentences: List[str] = []
    for s in raw_sentences:
        parts = re.split(r"\n{2,}", s)
        for p in parts:
            p = p.strip()
            if p:
                sentences.append(p)

    return sentences