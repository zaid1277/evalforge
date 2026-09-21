"""
Paragraph-aware text chunking.

The approach is deliberately simple: split the source's cleaned text into
paragraphs, then accumulate paragraphs into a chunk until adding the next
paragraph would push it past a target word count, starting a new chunk at
that point. Paragraph order is always preserved, and no wording is ever
changed -- only how the text is grouped into pieces.

This is pure text-in/text-out logic with no database or FastAPI
dependency, so it can be unit tested directly (see tests/test_chunking.py).
No LLM, embeddings, or NLP library is used anywhere here.
"""

import re

# A paragraph is separated from the next by a blank line. document_service's
# clean_text() already normalizes line endings, so "\n\n" is reliable here.
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\n+")

# Splits after a sentence-ending punctuation mark followed by whitespace.
# This is a simple heuristic, not real sentence tokenization -- good enough
# for breaking an oversized paragraph into readable pieces.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def count_words(text: str) -> int:
    """Approximate word count. Not a model token count -- see PRD notes."""
    return len(text.split())


def split_into_paragraphs(text: str) -> list[str]:
    """Split text on blank lines, dropping empty/whitespace-only paragraphs."""
    if not text:
        return []
    return [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]


def chunk_text(
    text: str,
    target_words: int = 750,
    max_words: int = 1000,
) -> list[str]:
    """Split text into ordered, paragraph-aware chunks.

    Paragraphs are added to the current chunk until doing so would exceed
    `target_words`, at which point a new chunk starts. A paragraph bigger
    than `max_words` on its own is split independently (see
    _split_oversized_paragraph) rather than forcing it into one chunk.

    Deterministic: the same input and configuration always produce the
    same output. Never pads, rewrites, or drops text -- only regroups it.
    """
    paragraphs = split_into_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush_current() -> None:
        nonlocal current, current_words
        if current:
            chunks.append("\n\n".join(current))
        current = []
        current_words = 0

    for paragraph in paragraphs:
        paragraph_words = count_words(paragraph)

        if paragraph_words > max_words:
            # This single paragraph is bigger than a whole chunk should be.
            # Finish the chunk being built, split the paragraph on its own,
            # and continue with a clean slate.
            flush_current()
            chunks.extend(_split_oversized_paragraph(paragraph, target_words, max_words))
            continue

        if current and current_words + paragraph_words > target_words:
            flush_current()

        current.append(paragraph)
        current_words += paragraph_words

    flush_current()
    return chunks


def _split_oversized_paragraph(paragraph: str, target_words: int, max_words: int) -> list[str]:
    """Split one oversized paragraph using sentence boundaries.

    Sentences are accumulated the same way paragraphs are above. If even a
    single "sentence" is still bigger than max_words (e.g. a long run of
    text with no punctuation), fall back to a plain word-count split --
    simple and predictable, with no NLP library involved.
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]

    pieces: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush_current() -> None:
        nonlocal current, current_words
        if current:
            pieces.append(" ".join(current))
        current = []
        current_words = 0

    for sentence in sentences:
        sentence_words = count_words(sentence)

        if sentence_words > max_words:
            flush_current()
            pieces.extend(_split_by_word_count(sentence, target_words))
            continue

        if current and current_words + sentence_words > target_words:
            flush_current()

        current.append(sentence)
        current_words += sentence_words

    flush_current()
    return pieces


def _split_by_word_count(text: str, size: int) -> list[str]:
    """Fallback split: cut the text into fixed-size word groups."""
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]
