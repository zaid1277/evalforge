"""
Dataset export (M8): reviewed EvaluationCase rows -> portable JSONL/CSV
files.

Export only ever *reads* already-persisted data. It never calls Gemini
and never recalculates duplicate_score or grounding_score -- both are
read straight from the database exactly as last computed by M6/M7. This
module deliberately does not import embedding_service, duplicate_service,
or grounding_service, so there is no code path here that could trigger a
model load.
"""

import csv
import io
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import SourceChunk
from app.models.evaluation_case import EvaluationCase
from app.models.evaluation_case_source import EvaluationCaseSource

# Column order for both JSONL keys and CSV headers. Deliberately excludes
# the *computed* is_possible_duplicate/needs_grounding_review flags (see
# schemas/evaluation_case.py) -- those depend on the currently configured
# threshold, not just the data, so the underlying duplicate_score/
# grounding_score are exported instead as the more portable values.
EXPORT_FIELDS = [
    "id",
    "question",
    "reference_answer",
    "category",
    "difficulty",
    "test_type",
    "is_answerable",
    "status",
    "source_chunk_ids",
    "duplicate_score",
    "grounding_score",
    "created_at",
]


def get_source_chunk_ids(db: Session, case_id: int) -> list[int]:
    """Deterministic (document order) source chunk IDs for one case -- the
    same ordering used everywhere else evidence is shown (see
    api/evaluation_cases.py's get_case_sources and grounding_service.py's
    get_combined_evidence_text). Reads the real persisted
    EvaluationCaseSource links; nothing is regenerated or guessed."""
    stmt = (
        select(SourceChunk.id)
        .join(EvaluationCaseSource, EvaluationCaseSource.source_chunk_id == SourceChunk.id)
        .where(EvaluationCaseSource.evaluation_case_id == case_id)
        .order_by(SourceChunk.source_document_id, SourceChunk.chunk_index)
    )
    return list(db.scalars(stmt).all())


def case_to_dict(db: Session, case: EvaluationCase) -> dict:
    """One case as a plain, portable dict -- no SQLAlchemy internals, no
    ORM objects, just the fields a dataset consumer outside EvalForge
    would need."""
    return {
        "id": case.id,
        "question": case.question,
        # Explicitly null (not "Not provided") for unanswerable cases --
        # that phrase is UI presentation only, not real data.
        "reference_answer": case.reference_answer,
        "category": case.category,
        "difficulty": case.difficulty.value,
        "test_type": case.test_type.value,
        "is_answerable": case.is_answerable,
        "status": case.status.value,
        "source_chunk_ids": get_source_chunk_ids(db, case.id),
        "duplicate_score": case.duplicate_score,
        "grounding_score": case.grounding_score,
        "created_at": case.created_at.isoformat(),
    }


def serialize_jsonl(db: Session, cases: list[EvaluationCase]) -> str:
    """One JSON object per line (JSONL), not a single JSON array.
    ensure_ascii=False keeps non-English characters readable rather than
    escaped as \\uXXXX."""
    lines = [json.dumps(case_to_dict(db, case), ensure_ascii=False) for case in cases]
    return "\n".join(lines) + ("\n" if lines else "")


def serialize_csv(db: Session, cases: list[EvaluationCase]) -> str:
    """A standard CSV file via csv.DictWriter, which correctly escapes
    commas, quotes, and embedded newlines in question/reference_answer --
    never hand-built by string concatenation.

    source_chunk_ids becomes a pipe-separated string (e.g. "3|4") rather
    than comma-separated, so it never needs its own CSV quoting just to
    stay a single cell. reference_answer is an empty cell (not the string
    "None") for unanswerable cases.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()

    for case in cases:
        row = case_to_dict(db, case)
        row["source_chunk_ids"] = "|".join(str(chunk_id) for chunk_id in row["source_chunk_ids"])
        if row["reference_answer"] is None:
            row["reference_answer"] = ""
        writer.writerow(row)

    return buffer.getvalue()


# Only lowercase letters, digits, and hyphens survive -- everything else
# (spaces, slashes, punctuation, emoji, newlines) is collapsed away. This
# is what makes it safe to put the result directly into an HTTP header.
_UNSAFE_FILENAME_CHARS_RE = re.compile(r"[^a-z0-9]+")


def build_export_filename(project_name: str, status_filter: str, export_format: str) -> str:
    """Turn an arbitrary, user-supplied project name into a safe filename.

    Never places raw user input into a filename or HTTP header: the
    project name is slugified down to a safe character set first, with a
    fixed fallback if that leaves nothing usable.
    """
    slug = _UNSAFE_FILENAME_CHARS_RE.sub("-", project_name.strip().lower()).strip("-")
    if not slug:
        slug = "evalforge-dataset"
    slug = slug[:80]  # reasonable max length

    extension = "jsonl" if export_format == "jsonl" else "csv"
    return f"{slug}-{status_filter}.{extension}"
