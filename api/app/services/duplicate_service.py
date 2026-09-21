"""
Semantic duplicate detection for evaluation case questions (M6).

For every case in a project, this computes the highest cosine similarity
between its question and every *other* case's question in that same
project, and stores that single number as `EvaluationCase.duplicate_score`.
A high score is a hint that two questions probably ask almost the same
thing -- it's advisory information for the human reviewer (see M5), never
an automatic deletion or rejection.

Only questions are compared -- never reference answers or source chunks
(that's out of scope for M6; grounding is M7). Comparison covers every
case in the project regardless of status (generated/approved/rejected),
so a reviewer gets full visibility, and never crosses project boundaries.

Scale: with a 50-case generation ceiling, comparing every pair of cases
is at most ~1,225 comparisons -- trivial to do in plain Python with numpy,
so no vector database or approximate-nearest-neighbor index is needed
here.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evaluation_case import EvaluationCase
from app.services.embedding_service import cosine_similarity, embed_texts

logger = logging.getLogger(__name__)


def recalculate_project_duplicate_scores(db: Session, project_id: int) -> None:
    """Recompute and persist `duplicate_score` for every case in a project.

    All-or-nothing: embeddings for every case are computed first, and
    nothing is written to the database until every score is known. If
    embedding fails partway through, an exception propagates and no
    scores are changed -- callers should treat a failure here as
    non-fatal to whatever generated/edited the case that triggered it
    (see generation_service.py / review_service.py), since a scoring
    failure must never corrupt already-valid case data.
    """
    cases = list(db.scalars(select(EvaluationCase).where(EvaluationCase.project_id == project_id)))

    if len(cases) < 2:
        # Nothing to compare against -- a single case (or none) has no
        # "other case" to be a duplicate of.
        for case in cases:
            case.duplicate_score = None
        db.commit()
        return

    # One batched model call for every question in the project, rather
    # than one call per question (see embedding_service.embed_texts).
    vectors = embed_texts([case.question for case in cases])

    scores = _pairwise_max_similarity(vectors)
    for case, score in zip(cases, scores):
        case.duplicate_score = score

    db.commit()


def _pairwise_max_similarity(vectors) -> list[float]:
    """For each vector, the highest cosine similarity against any other
    vector in the list. Self-comparison is skipped by only ever comparing
    (i, j) pairs where j > i.

    Example, for cases A, B, C, D:
        A vs B = 0.94
        A vs C = 0.63
        A vs D = 0.45
        -> A's duplicate_score = 0.94 (the highest of the three)
    """
    n = len(vectors)
    # Every index is guaranteed at least one comparison here (n >= 2), so
    # -inf is always overwritten -- it's just a safe starting point, never
    # a real returned value.
    best = [float("-inf")] * n

    for i in range(n):
        for j in range(i + 1, n):
            score = cosine_similarity(vectors[i], vectors[j])
            if score > best[i]:
                best[i] = score
            if score > best[j]:
                best[j] = score

    return best
