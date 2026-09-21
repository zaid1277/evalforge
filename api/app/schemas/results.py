"""
Schemas for the M10 results dashboard -- purely derived analytics over
already-persisted M9 EvaluationRun/EvaluationResult rows. Nothing here is
stored; these are read-only response shapes for
GET /evaluations/{id}/dashboard.
"""

from datetime import datetime

from pydantic import BaseModel


class MetricBreakdown(BaseModel):
    """total/passed/failed/pass_rate for one slice of results (e.g. one
    test type, one difficulty). `pass_rate` is `None` (not `0.0`) when
    `total` is 0 -- an empty category has no pass rate to report, and
    showing 0% would misleadingly read as "the model failed everything
    in this category" when really there was nothing to evaluate.
    """

    total: int
    passed: int
    failed: int
    pass_rate: float | None


class EvaluationDashboardResponse(BaseModel):
    """GET /evaluations/{id}/dashboard.

    total_cases/passed_cases/failed_cases/pass_rate here are freshly
    derived by counting this run's actual EvaluationResult rows (see
    services/results_service.py), not merely copied from
    EvaluationRun.total_cases/passed_cases/failed_cases -- see that
    module for the consistency check against the stored columns.
    """

    evaluation_id: int
    project_id: int
    provider: str
    model_name: str
    created_at: datetime

    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float | None

    # Keyed by TestType.value ("direct", "multi_step", "unanswerable") /
    # Difficulty.value ("easy", "medium") / "answerable" | "unanswerable".
    # Every key is always present, even with total=0, so the frontend
    # never has to guess whether a category was merely empty vs omitted.
    by_test_type: dict[str, MetricBreakdown]
    by_difficulty: dict[str, MetricBreakdown]
    by_answerability: dict[str, MetricBreakdown]
