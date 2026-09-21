"""
Model evaluation pipeline (M9): approved EvaluationCases -> target model
responses -> scored EvaluationResults -> one persisted EvaluationRun.

    Approved EvaluationCases (project-scoped, id ASC)
    -> provider.generate_response(question)  [question ONLY -- see below]
    -> answerable cases:   MiniLM cosine_similarity(response, reference_answer)
                            -> threshold -> pass/fail
    -> unanswerable cases: provider.judge_unanswerable_response(question, response)
                            -> pass/fail
    -> EvaluationRun + EvaluationResults, written in ONE transaction

Provider input safety: the target model only ever receives the case's
`question` (via provider.generate_response). It is never given
reference_answer, duplicate_score, grounding_score, or review status --
sending any of those would leak the expected answer into the thing being
evaluated.

Atomicity: everything above is computed in memory first. Nothing is
added to the database session until every case has a model response and
a score/verdict -- only then are the EvaluationRun and all of its
EvaluationResult rows created and committed together. If any provider
call fails (target response, or the judge after its one allowed retry),
this raises before anything is added to the session, so a failed run
never leaves a half-complete run or orphaned results behind. This is why
EvaluationRun has no `status` column: every row that exists represents a
complete run.

Reuses the exact same MiniLM embedding infrastructure as M6/M7
(embedding_service.embed_texts/cosine_similarity) -- no second model,
and this module never recalculates duplicate_score or grounding_score
(those belong to dataset-quality review, a separate concern).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.evaluation_case import EvaluationCase, EvaluationStatus
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_run import EvaluationRun
from app.providers.base import JudgeResult, LLMProvider, ProviderResponseError
from app.services.embedding_service import cosine_similarity, embed_texts

logger = logging.getLogger(__name__)

# Initial attempt + this many retries, for the judge call only (PRD:
# "maximum one retry for malformed structured judge output"). Target
# response generation (plain text, not structured) is not retried here --
# a failure there is a hard provider error, not "malformed output".
MAX_JUDGE_RETRIES = 1


class EvaluationError(Exception):
    """Base class for evaluation failures; the route layer maps these to
    HTTP responses."""


class NoApprovedCasesError(EvaluationError):
    pass


class EvaluationLimitExceededError(EvaluationError):
    pass


class EvaluationFailedError(EvaluationError):
    pass


def evaluate_project(
    db: Session,
    project_id: int,
    provider: LLMProvider,
    provider_name: str,
    model_name: str,
) -> EvaluationRun:
    cases = _approved_cases(db, project_id)
    if not cases:
        raise NoApprovedCasesError("No approved evaluation cases are available to evaluate.")

    if len(cases) > settings.MAX_EVALUATION_CASES:
        raise EvaluationLimitExceededError(
            f"Dataset contains {len(cases)} approved cases but the evaluation "
            f"limit is {settings.MAX_EVALUATION_CASES}."
        )

    logger.info(
        "evaluation started: project_id=%s case_count=%s provider=%s model=%s",
        project_id, len(cases), provider_name, model_name,
    )

    pending = [_PendingResult(case) for case in cases]

    for entry in pending:
        # Only the bare question is ever sent -- never reference_answer,
        # duplicate_score, grounding_score, or status.
        try:
            entry.model_response = provider.generate_response(entry.case.question)
        except ProviderResponseError as exc:
            raise EvaluationFailedError(
                f"Evaluation failed while generating a target model response: {exc}"
            ) from exc

    _score_answerable(pending)
    _judge_unanswerable(provider, pending)

    run = _build_run(project_id, provider_name, model_name, pending)
    db.add(run)
    db.commit()
    db.refresh(run)
    for result in run.results:
        db.refresh(result)

    logger.info(
        "evaluation succeeded: project_id=%s run_id=%s total=%s passed=%s failed=%s",
        project_id, run.id, run.total_cases, run.passed_cases, run.failed_cases,
    )

    return run


class _PendingResult:
    """In-memory accumulator for one case's evaluation outcome, before
    anything is written to the database. Deliberately not an ORM object
    yet -- see the atomicity note in the module docstring."""

    def __init__(self, case: EvaluationCase):
        self.case = case
        self.model_response: str = ""
        self.semantic_similarity: float | None = None
        self.passed: bool = False
        self.evaluation_reason: str = ""


def _approved_cases(db: Session, project_id: int) -> list[EvaluationCase]:
    stmt = (
        select(EvaluationCase)
        .where(
            EvaluationCase.project_id == project_id,
            EvaluationCase.status == EvaluationStatus.APPROVED,
        )
        .order_by(EvaluationCase.id.asc())
    )
    return list(db.scalars(stmt).all())


def _score_answerable(pending: list["_PendingResult"]) -> None:
    """Batch-score every answerable case in one embedding call: N
    reference answers + N model responses -> one embed_texts() call,
    rather than one model call per case (mirrors
    grounding_service.recalculate_grounding_for_cases)."""
    answerable = [entry for entry in pending if entry.case.is_answerable]
    if not answerable:
        return

    reference_answers = [entry.case.reference_answer for entry in answerable]
    model_responses = [entry.model_response for entry in answerable]
    vectors = embed_texts(reference_answers + model_responses)

    n = len(answerable)
    for i, entry in enumerate(answerable):
        similarity = cosine_similarity(vectors[i], vectors[n + i])
        entry.semantic_similarity = similarity
        entry.passed = similarity >= settings.ANSWER_SIMILARITY_THRESHOLD
        entry.evaluation_reason = _answerable_reason(entry.passed, similarity)


def _answerable_reason(passed: bool, similarity: float) -> str:
    # This is a heuristic result, not a correctness guarantee -- semantic
    # similarity captures topical/wording relatedness, not fact-checking
    # (see the ANSWER_SIMILARITY_THRESHOLD comment in app/config.py).
    if passed:
        return (
            f"Model response was semantically similar to the reference answer "
            f"(similarity: {similarity:.2f})."
        )
    return (
        f"Model response had low semantic similarity to the reference answer "
        f"(similarity: {similarity:.2f})."
    )


def _judge_unanswerable(provider: LLMProvider, pending: list["_PendingResult"]) -> None:
    """Sequential (not batched -- each is a real LLM/judge call), with at
    most one retry per case for malformed structured output."""
    for entry in pending:
        if entry.case.is_answerable:
            continue
        result = _judge_with_retry(provider, entry.case.question, entry.model_response)
        entry.semantic_similarity = None
        entry.passed = result.passed
        entry.evaluation_reason = result.reason


def _judge_with_retry(provider: LLMProvider, question: str, model_response: str) -> JudgeResult:
    last_error: ProviderResponseError | None = None

    for attempt in range(1 + MAX_JUDGE_RETRIES):
        try:
            return provider.judge_unanswerable_response(question, model_response)
        except ProviderResponseError as exc:
            last_error = exc
            logger.warning("judge validation failed on attempt %d: %s", attempt + 1, exc)

    raise EvaluationFailedError(
        "Evaluation failed: the judge returned invalid data after a retry."
    ) from last_error


def _build_run(
    project_id: int,
    provider_name: str,
    model_name: str,
    pending: list["_PendingResult"],
) -> EvaluationRun:
    passed_count = sum(1 for entry in pending if entry.passed)

    run = EvaluationRun(
        project_id=project_id,
        provider=provider_name,
        model_name=model_name,
        total_cases=len(pending),
        passed_cases=passed_count,
        failed_cases=len(pending) - passed_count,
    )
    run.results = [
        EvaluationResult(
            evaluation_case_id=entry.case.id,
            question_snapshot=entry.case.question,
            reference_answer_snapshot=entry.case.reference_answer,
            test_type_snapshot=entry.case.test_type,
            difficulty_snapshot=entry.case.difficulty,
            model_response=entry.model_response,
            semantic_similarity=entry.semantic_similarity,
            passed=entry.passed,
            evaluation_reason=entry.evaluation_reason,
        )
        for entry in pending
    ]
    return run
