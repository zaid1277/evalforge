"""
Schemas for model evaluation (M9).

`JudgeVerdict` is the trust boundary for the unanswerable-case judge,
exactly parallel to how `GeneratedCase` (schemas/generation.py) is the
trust boundary for generation output -- raw Gemini JSON is never treated
as a real pass/fail result until it passes through this validation.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.evaluation_case import Difficulty, TestType


class JudgeVerdict(BaseModel):
    """Raw structured output from an unanswerable-case judge call. The
    judge prompt (providers/prompts.py) asks for a JSON key literally
    named "pass" -- reserved in Python, so the attribute here is
    `passed`, aliased to "pass" for (de)serialization.
    """

    passed: bool = Field(alias="pass")
    reason: str = Field(min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class EvaluationRequest(BaseModel):
    """POST /projects/{id}/evaluations body.

    Deliberately empty for M9: the provider and model always come from
    backend configuration (LLM_PROVIDER/GEMINI_MODEL/USE_MOCK_LLM in
    app/config.py), never from the request -- the frontend cannot select
    a provider, and no API key is ever accepted here. Kept as its own
    model (rather than no body at all) so a future milestone could add an
    optional field without changing the endpoint signature.
    """


class EvaluationResultResponse(BaseModel):
    id: int
    evaluation_case_id: int
    # Exposed under their pre-M9 names (question/reference_answer/...)
    # even though they're read from this result's *snapshot* columns
    # (question_snapshot/...) -- see models/evaluation_result.py for why
    # a snapshot is taken instead of reading the live case.
    question: str = Field(validation_alias="question_snapshot")
    reference_answer: str | None = Field(validation_alias="reference_answer_snapshot")
    model_response: str
    semantic_similarity: float | None
    passed: bool
    evaluation_reason: str
    test_type: TestType = Field(validation_alias="test_type_snapshot")
    difficulty: Difficulty = Field(validation_alias="difficulty_snapshot")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class EvaluationRunSummary(BaseModel):
    """GET /projects/{id}/evaluations -- history list. No results payload,
    just enough to show one row per past run."""

    id: int
    project_id: int
    provider: str
    model_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunResponse(EvaluationRunSummary):
    """POST /projects/{id}/evaluations and GET /evaluations/{id} -- the
    summary plus every individual result."""

    results: list[EvaluationResultResponse]
