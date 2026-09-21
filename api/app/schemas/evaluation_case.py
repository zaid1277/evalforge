from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.config import settings
from app.models.evaluation_case import Difficulty, EvaluationStatus, TestType


class EvaluationCaseResponse(BaseModel):
    id: int
    project_id: int
    question: str
    reference_answer: str | None
    category: str
    difficulty: Difficulty
    test_type: TestType
    is_answerable: bool
    status: EvaluationStatus
    source_chunk_ids: list[int]
    # Highest cosine similarity to another case's question in this project
    # (see services/duplicate_service.py). Null until compared.
    duplicate_score: float | None
    # Cosine similarity between reference_answer and its exact linked
    # source evidence (see services/grounding_service.py). Always null
    # for unanswerable cases -- there is no reference_answer to compare.
    grounding_score: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def is_possible_duplicate(self) -> bool:
        """Server-side threshold check, not a persisted column -- the
        frontend never needs to know the threshold itself."""
        return (
            self.duplicate_score is not None
            and self.duplicate_score >= settings.DUPLICATE_SIMILARITY_THRESHOLD
        )

    @computed_field
    @property
    def needs_grounding_review(self) -> bool:
        """Server-side threshold check, not persisted. Always False for
        unanswerable cases (grounding_score is null for them)."""
        return (
            self.grounding_score is not None
            and self.grounding_score < settings.GROUNDING_SIMILARITY_THRESHOLD
        )


class EvaluationCaseUpdate(BaseModel):
    """PATCH payload for manual review (M5).

    Every field is optional -- the frontend only sends what's actually
    changing (e.g. just `{"status": "approved"}`). `id`, `project_id`,
    `created_at`, and `source_chunk_ids` are deliberately absent: none of
    them can be edited through this endpoint.
    """

    question: str | None = None
    reference_answer: str | None = None
    category: str | None = None
    difficulty: Difficulty | None = None
    test_type: TestType | None = None
    is_answerable: bool | None = None
    status: EvaluationStatus | None = None
