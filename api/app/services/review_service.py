"""
Manual review of generated evaluation cases (M5).

Generated evaluation data is not trusted just because an LLM produced it
-- a human reviews it, optionally edits it, and marks it approved or
rejected. Edited cases must obey the exact same answerability rules as
freshly generated ones, so this reuses `GeneratedCase` (see
schemas/generation.py) rather than maintaining a second, possibly
inconsistent set of validation rules.

The key subtlety is that a PATCH is validated as *the resulting whole
case* (existing values merged with the patch), not just the fields that
were sent. That's what makes a PATCH like {"reference_answer": ""} against
an already-answerable case fail, even though that single field looks
harmless in isolation.
"""

import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.evaluation_case import EvaluationCase, TestType
from app.schemas.evaluation_case import EvaluationCaseUpdate
from app.schemas.generation import GeneratedCase
from app.services.duplicate_service import recalculate_project_duplicate_scores
from app.services.grounding_service import recalculate_case_grounding

logger = logging.getLogger(__name__)


class CaseValidationError(ValueError):
    """The resulting case (existing values + patch) would be invalid."""


def apply_case_update(db: Session, case: EvaluationCase, update: EvaluationCaseUpdate) -> EvaluationCase:
    # `exclude_unset` is what lets a PATCH omit fields entirely rather than
    # having to resend the whole case -- only keys actually present in the
    # request body end up here (even if their value is None).
    patch = update.model_dump(exclude_unset=True)
    new_status = patch.pop("status", None)

    merged = {
        "question": case.question,
        "reference_answer": case.reference_answer,
        "category": case.category,
        "difficulty": case.difficulty,
        "test_type": case.test_type,
        "is_answerable": case.is_answerable,
    }
    merged.update(patch)

    # Changing test_type is the one edit that implies other fields. Fill in
    # sane defaults only where the reviewer didn't explicitly set them --
    # an explicit, genuinely contradictory combination (e.g. test_type=
    # unanswerable with is_answerable=true sent together) is left alone
    # here and caught by validation below, rather than silently "fixed".
    if "test_type" in patch:
        new_test_type = patch["test_type"]
        if "is_answerable" not in patch:
            merged["is_answerable"] = new_test_type != TestType.UNANSWERABLE
        if new_test_type == TestType.UNANSWERABLE and "reference_answer" not in patch:
            merged["reference_answer"] = None

    # Source chunk links are fixed during review -- always revalidate
    # against the case's real, unchanged evidence.
    merged["source_chunk_ids"] = case.source_chunk_ids

    try:
        validated = GeneratedCase(**merged)
    except ValidationError as exc:
        raise CaseValidationError(_first_error_message(exc)) from exc

    question_changed = validated.question != case.question
    reference_answer_changed = validated.reference_answer != case.reference_answer
    answerability_changed = validated.is_answerable != case.is_answerable

    case.question = validated.question
    case.reference_answer = validated.reference_answer
    case.category = validated.category
    case.difficulty = validated.difficulty
    case.test_type = validated.test_type
    case.is_answerable = validated.is_answerable

    if new_status is not None:
        case.status = new_status

    db.commit()
    db.refresh(case)

    # Duplicate scores depend only on question text (see
    # duplicate_service.py) -- editing the reference answer, category,
    # difficulty, test_type, or status alone never needs a recalculation.
    if question_changed:
        try:
            recalculate_project_duplicate_scores(db, case.project_id)
        except Exception:
            logger.exception(
                "duplicate score recalculation failed after editing case_id=%s", case.id
            )
        else:
            db.refresh(case)

    # Grounding depends only on reference_answer + linked evidence (see
    # grounding_service.py) -- a *different* trigger from duplicate
    # detection above. Editing the question, category, difficulty, or
    # status alone never needs a recalculation here. An answerability
    # change matters even without a reference_answer change too: becoming
    # unanswerable must clear the score to null, and becoming answerable
    # needs a fresh score computed against the (unchanged) evidence.
    if reference_answer_changed or answerability_changed:
        try:
            recalculate_case_grounding(db, case)
        except Exception:
            logger.exception(
                "grounding score recalculation failed after editing case_id=%s", case.id
            )
        else:
            db.refresh(case)

    return case


def _first_error_message(exc: ValidationError) -> str:
    """A short, user-facing message instead of Pydantic's full error dump."""
    errors = exc.errors()
    if errors:
        return str(errors[0]["msg"])
    return "Invalid evaluation case update."
