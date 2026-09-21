"""
Grounding heuristic for answerable evaluation cases (M7).

For an answerable case, this checks whether its reference answer is
semantically related to the *exact* source evidence already linked to it
via EvaluationCaseSource (see M4) -- never the whole project, never a
"better" chunk found by search. It reuses the same MiniLM embedding
infrastructure introduced for duplicate detection in M6 (see
embedding_service.py) rather than a second model.

    reference answer  --MiniLM-->  vector
    linked evidence   --MiniLM-->  vector
                        cosine similarity
                              |
                       grounding_score

This is a heuristic, not a factual-correctness check: a high score means
the answer's wording is semantically related to its evidence; a low
score means a human should look closer -- it does not mean the case is
wrong, incorrect, or hallucinated.

Unanswerable cases have no reference answer, so grounding_score is
always null for them -- there is nothing to compare.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import SourceChunk
from app.models.evaluation_case import EvaluationCase
from app.models.evaluation_case_source import EvaluationCaseSource
from app.services.embedding_service import cosine_similarity, embed_texts

logger = logging.getLogger(__name__)


def is_groundable(case: EvaluationCase) -> bool:
    """Only answerable cases with an actual reference answer can be
    grounded -- unanswerable cases intentionally have neither."""
    return case.is_answerable and bool(case.reference_answer)


def get_combined_evidence_text(db: Session, case_id: int) -> str:
    """The exact chunks linked via EvaluationCaseSource, in the same
    document order shown to the reviewer (GET /cases/{id}/sources),
    joined into one string.

    For a multi-step case (up to 2 linked chunks) this simply
    concatenates them in that order -- no weighting, reranking, or
    picking a "better" chunk. A reference answer that draws on either or
    both chunks should still read as related to this combined text.
    """
    stmt = (
        select(SourceChunk)
        .join(EvaluationCaseSource, EvaluationCaseSource.source_chunk_id == SourceChunk.id)
        .where(EvaluationCaseSource.evaluation_case_id == case_id)
        .order_by(SourceChunk.source_document_id, SourceChunk.chunk_index)
    )
    chunks = db.scalars(stmt).all()
    return "\n\n".join(chunk.text for chunk in chunks)


def calculate_grounding_score(reference_answer: str, evidence_text: str) -> float:
    """One cosine similarity between a reference answer and its evidence."""
    vectors = embed_texts([reference_answer, evidence_text])
    return cosine_similarity(vectors[0], vectors[1])


def recalculate_case_grounding(db: Session, case: EvaluationCase) -> float | None:
    """Recompute and persist grounding_score for a single case (used when
    only one case needs it, e.g. after a reference-answer edit)."""
    recalculate_grounding_for_cases(db, [case])
    db.refresh(case)
    return case.grounding_score


def recalculate_grounding_for_cases(db: Session, cases: list[EvaluationCase]) -> None:
    """Recompute grounding_score for several cases at once.

    Batches the embedding call: every reference answer and every evidence
    text across all the given cases is encoded in a single embed_texts()
    call, rather than one model call per case. All-or-nothing, like
    duplicate_service.py -- if the batched embedding call fails, nothing
    below has been written yet, so no score is fabricated and nothing
    already-valid is corrupted.
    """
    scorable: list[tuple[EvaluationCase, str, str]] = []

    for case in cases:
        if not is_groundable(case):
            case.grounding_score = None
            continue

        evidence_text = get_combined_evidence_text(db, case.id)
        if not evidence_text:
            # Shouldn't normally happen -- generation always links at
            # least one chunk -- but fail safe rather than fabricate a
            # score for a case with nothing to compare against.
            logger.warning(
                "case_id=%s is answerable but has no linked evidence text", case.id
            )
            case.grounding_score = None
            continue

        scorable.append((case, case.reference_answer, evidence_text))

    if scorable:
        # One batched call covering every reference answer AND every
        # evidence text for every case being recalculated here.
        reference_answers = [ref for _, ref, _ in scorable]
        evidence_texts = [ev for _, _, ev in scorable]
        vectors = embed_texts(reference_answers + evidence_texts)

        n = len(scorable)
        for index, (case, _, _) in enumerate(scorable):
            case.grounding_score = cosine_similarity(vectors[index], vectors[n + index])

    db.commit()
