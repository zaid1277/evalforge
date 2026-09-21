"""
Source document text extraction and cleaning.

This is intentionally simple: decode/extract raw text, then apply
conservative whitespace normalization. No chunking, no LLM calls, and no
OCR -- those are out of scope until later milestones (see PRD sections 8-9
and the M2 scope notes). The cleanup here never changes wording, so the
factual content of a source is preserved exactly as extracted.
"""

import re
from io import BytesIO

from pypdf import PdfReader

from app.models.source import SourceType


class DocumentError(ValueError):
    """A source document can't be read, or contains no usable text.

    Routes catch this and turn it into a 400 response with the message
    as-is, so messages here should be safe to show to the user.
    """


# Only these extensions are accepted. An upload's SourceType is always
# derived from this table -- never taken directly from user input.
EXTENSION_TO_SOURCE_TYPE = {
    ".txt": SourceType.TXT,
    ".md": SourceType.MARKDOWN,
    ".pdf": SourceType.PDF,
}


def source_type_for_filename(filename: str) -> SourceType:
    """Map an uploaded filename's extension to a controlled SourceType."""
    suffix = _extension(filename)
    source_type = EXTENSION_TO_SOURCE_TYPE.get(suffix)
    if source_type is None:
        allowed = ", ".join(sorted(EXTENSION_TO_SOURCE_TYPE))
        label = suffix or filename or "(no filename)"
        raise DocumentError(f"Unsupported file type '{label}'. Allowed types: {allowed}.")
    return source_type


def _extension(filename: str) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def safe_filename(filename: str | None) -> str:
    """Sanitize a filename for storage/display.

    We never write this to disk or build a filesystem path with it, but
    it's still shown back to the user, so strip any path separators a
    client might send and cap the length.
    """
    name = (filename or "upload").strip().replace("\\", "/")
    name = name.rsplit("/", 1)[-1]
    return name[:255] or "upload"


def clean_text(text: str) -> str:
    """Conservative whitespace cleanup.

    Normalizes line endings, collapses 3+ blank lines down to one, and
    trims trailing whitespace per line and around the whole document.
    Never removes or rewrites words -- only whitespace.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def require_meaningful_text(text: str, *, empty_message: str) -> None:
    """Reject empty or whitespace-only text with a caller-supplied message."""
    if not text or not text.strip():
        raise DocumentError(empty_message)


def decode_text_file(raw_bytes: bytes) -> str:
    """Decode a .txt/.md upload as UTF-8 and apply the standard cleanup."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError("Unable to read file: not valid UTF-8 text.") from exc
    return clean_text(text)


def extract_pdf_text(raw_bytes: bytes) -> str:
    """Extract text from a PDF that has a real text layer, page by page.

    This only reads text pypdf can already find in the PDF's content
    streams -- it does not render pages to images or run OCR, so scanned
    (image-only) PDFs correctly produce no text and are rejected below.
    """
    try:
        reader = PdfReader(BytesIO(raw_bytes))
    except Exception as exc:  # pypdf raises several error types for corrupt files
        raise DocumentError("Unable to read file: not a valid PDF.") from exc

    page_texts = [page.extract_text() or "" for page in reader.pages]
    combined = clean_text("\n\n".join(page_texts))

    require_meaningful_text(
        combined,
        empty_message=(
            "No extractable text was found in this PDF. "
            "OCR is not supported in the current version."
        ),
    )
    return combined
