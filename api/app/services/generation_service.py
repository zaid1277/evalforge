"""
Generation pipeline: SourceChunks -> provider -> validated cases -> DB.

    Project
    -> SourceChunks (already extracted/chunked in M2/M3)
    -> this service builds small batches and calls the configured provider
    -> every case the provider returns goes through GeneratedCase (Pydantic)
       plus a chunk-ownership check
    -> only if a whole request's worth of cases validates cleanly are any
       EvaluationCase/EvaluationCaseSource rows written, in one transaction

No embeddings, duplicate detection, or grounding scoring happens here --
those are M6/M7. "Grounding" in M4 only means: every source_chunk_id a
case references must be a real chunk belonging to this project.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import SourceChunk
from app.models.evaluation_case import EvaluationCase, EvaluationStatus
from app.models.evaluation_case_source import EvaluationCaseSource
from app.models.source import SourceDocument
from app.providers.base import ChunkInput, LLMProvider, ProviderResponseError
from app.schemas.generation import GeneratedCase, GenerationRequest
from app.services.duplicate_service import recalculate_project_duplicate_scores
from app.services.grounding_service import recalculate_grounding_for_cases

logger = logging.getLogger(__name__)

# Keep each provider call small and cheap rather than sending an entire
# project's worth of chunks in one request.
CHUNKS_PER_BATCH = 3

# Initial attempt + this many retries. PRD requires "at most one retry".
MAX_RETRIES = 1


class GenerationError(Exception):
    """Base class for generation failures; the route layer maps these to
    HTTP responses."""


class NoChunksAvailableError(GenerationError):
    pass


class GenerationFailedError(GenerationError):
    pass


def generate_evaluation_cases(
    db: Session,
    project_id: int,
    provider: LLMProvider,
    request: GenerationRequest,
) -> list[EvaluationCase]:
    chunks = _project_chunks(db, project_id)
    if not chunks:
        raise NoChunksAvailableError(
            "This project has no source chunks available for generation."
        )

    valid_chunk_ids = {chunk.id for chunk in chunks}
    batches = _batches(chunks, CHUNKS_PER_BATCH)
    test_type_values = [t.value for t in request.test_types]

    logger.info(
        "generation started: project_id=%s requested_count=%s difficulty=%s "
        "test_types=%s provider=%s",
        project_id, request.count, request.difficulty, test_type_values, type(provider).__name__,
    )

    generated: list[GeneratedCase] = []
    for batch in batches:
        if len(generated) >= request.count:
            break
        remaining = request.count - len(generated)
        # Ceiling-divide what's left across the remaining batches so a
        # single batch never has to cover far more than its fair share.
        batch_request_count = min(remaining, max(1, -(-request.count // len(batches))))

        generated.extend(
            _call_provider_with_retry(
                provider, batch, batch_request_count, request.difficulty,
                test_type_values, valid_chunk_ids,
            )
        )

    generated = generated[: request.count]

    saved_cases = [_build_case(project_id, case) for case in generated]
    db.add_all(saved_cases)
    db.commit()
    for case in saved_cases:
        db.refresh(case)

    logger.info("generation succeeded: project_id=%s saved_count=%s", project_id, len(saved_cases))

    # A newly generated case may become the closest semantic duplicate of
    # an *existing* case too, so the whole project is rescored, not just
    # the new rows. This is best-effort: the cases above are already
    # validly saved, so a scoring failure is logged and swallowed rather
    # than corrupting or hiding an otherwise-successful generation.
    try:
        recalculate_project_duplicate_scores(db, project_id)
    except Exception:
        logger.exception(
            "duplicate score recalculation failed after generation: project_id=%s", project_id
        )
    else:
        for case in saved_cases:
            db.refresh(case)

    # Same best-effort principle as duplicate scoring above: grounding is
    # advisory metadata, so a scoring failure here must never make an
    # already-validly-generated case disappear or look malformed.
    try:
        recalculate_grounding_for_cases(db, saved_cases)
    except Exception:
        logger.exception(
            "grounding score recalculation failed after generation: project_id=%s", project_id
        )
    else:
        for case in saved_cases:
            db.refresh(case)

    return saved_cases


def _project_chunks(db: Session, project_id: int) -> list[SourceChunk]:
    stmt = (
        select(SourceChunk)
        .join(SourceDocument, SourceChunk.source_document_id == SourceDocument.id)
        .where(SourceDocument.project_id == project_id)
        .order_by(SourceDocument.id, SourceChunk.chunk_index)
    )
    return list(db.scalars(stmt).all())


def _batches(chunks: list[SourceChunk], batch_size: int) -> list[list[SourceChunk]]:
    return [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]


def _call_provider_with_retry(
    provider: LLMProvider,
    batch: list[SourceChunk],
    request_count: int,
    difficulty: str,
    test_types: list[str],
    valid_chunk_ids: set[int],
) -> list[GeneratedCase]:
    """Call the provider, retrying at most once if the output is malformed
    (invalid JSON/schema, or a chunk reference outside this project).
    A hard provider error (e.g. bad API key, network failure) is not
    retried -- retrying that would just burn quota for no benefit.
    """
    chunk_inputs = [ChunkInput(id=chunk.id, text=chunk.text) for chunk in batch]
    last_error: ProviderResponseError | None = None

    for attempt in range(1 + MAX_RETRIES):
        try:
            cases = provider.generate_eval_cases(chunk_inputs, request_count, difficulty, test_types)
            _check_chunk_ownership(cases, valid_chunk_ids)
            return cases
        except ProviderResponseError as exc:
            last_error = exc
            logger.warning("generation validation failed on attempt %d: %s", attempt + 1, exc)

    raise GenerationFailedError(
        "Generation failed: the LLM provider returned invalid data after a retry."
    ) from last_error


def _check_chunk_ownership(cases: list[GeneratedCase], valid_chunk_ids: set[int]) -> None:
    for case in cases:
        if not set(case.source_chunk_ids) <= valid_chunk_ids:
            raise ProviderResponseError(
                "Generated case referenced a source chunk outside this project."
            )


def _build_case(project_id: int, case: GeneratedCase) -> EvaluationCase:
    db_case = EvaluationCase(
        project_id=project_id,
        question=case.question,
        reference_answer=case.reference_answer,
        category=case.category,
        difficulty=case.difficulty,
        test_type=case.test_type,
        is_answerable=case.is_answerable,
        status=EvaluationStatus.GENERATED,
    )
    db_case.source_links = [
        EvaluationCaseSource(source_chunk_id=chunk_id) for chunk_id in case.source_chunk_ids
    ]
    return db_case
