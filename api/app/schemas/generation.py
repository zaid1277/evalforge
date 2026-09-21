"""
Schemas for the generation pipeline.

`GeneratedCase` is the critical trust boundary: it's what every piece of
raw LLM output must pass through before EvalForge treats it as real data.
Nothing from a provider is ever persisted or returned to the frontend
without going through this validation first.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.evaluation_case import Difficulty, TestType
from app.schemas.evaluation_case import EvaluationCaseResponse

# What a generation request may ask for. "mixed" means the resulting cases
# may be a blend of easy/medium -- it is never stored on an individual case.
GenerationDifficulty = Literal["easy", "medium", "mixed"]

DEFAULT_TEST_TYPES = [TestType.DIRECT, TestType.MULTI_STEP, TestType.UNANSWERABLE]

# Multi-step cases may combine at most this many source chunks, so the
# reasoning stays understandable and tightly tied to evidence (PRD M4).
MAX_MULTI_STEP_CHUNKS = 2


class GeneratedCase(BaseModel):
    """One evaluation case as produced by an LLM provider, before it is
    persisted. Structural validation only -- checking that referenced
    chunks actually belong to the right project happens in
    generation_service.py, which has database access."""

    question: str = Field(min_length=1)
    reference_answer: str | None = None
    source_chunk_ids: list[int] = Field(min_length=1)
    category: str = Field(min_length=1)
    difficulty: Difficulty
    test_type: TestType
    is_answerable: bool

    @field_validator("question", "category")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("reference_answer")
    @classmethod
    def _normalize_reference_answer(cls, value: str | None) -> str | None:
        """Treat "", whitespace, or explicit null the same way: no answer."""
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _check_answerability_matches_reference_answer(self) -> "GeneratedCase":
        if self.is_answerable and not self.reference_answer:
            raise ValueError("answerable cases must include a meaningful reference_answer")
        if not self.is_answerable and self.reference_answer:
            raise ValueError(
                "unanswerable cases must not include a reference_answer "
                "(the model must not invent one)"
            )
        return self

    @model_validator(mode="after")
    def _check_test_type_matches_answerability(self) -> "GeneratedCase":
        expected_answerable = self.test_type != TestType.UNANSWERABLE
        if self.is_answerable != expected_answerable:
            raise ValueError("is_answerable must be consistent with test_type")
        return self

    @model_validator(mode="after")
    def _check_multi_step_chunk_limit(self) -> "GeneratedCase":
        if self.test_type == TestType.MULTI_STEP and len(self.source_chunk_ids) > MAX_MULTI_STEP_CHUNKS:
            raise ValueError(f"multi_step cases may reference at most {MAX_MULTI_STEP_CHUNKS} source chunks")
        return self


class GenerationRequest(BaseModel):
    count: int = Field(gt=0)
    difficulty: GenerationDifficulty = "mixed"
    test_types: list[TestType] = Field(default_factory=lambda: list(DEFAULT_TEST_TYPES), min_length=1)


class GenerationResponse(BaseModel):
    generated_count: int
    provider: str
    model: str
    cases: list[EvaluationCaseResponse]
