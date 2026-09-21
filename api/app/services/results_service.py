"""
Results dashboard aggregation (M10): turns one EvaluationRun's already-
persisted EvaluationResult rows into interpretable metrics.

This module is strictly read-only derived analytics -- it never calls
Gemini, never recalculates MiniLM semantic_similarity, never touches
duplicate_score/grounding_score, and never reruns or rescoring anything
from M9. It doesn't even import embedding_service or any provider: there
is no code path here that could trigger a model load or network call.
Every number below is computed by counting/grouping the EvaluationResult
rows already sitting in the database for this run.
"""

import logging

from app.models.evaluation_case import Difficulty, TestType
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_run import EvaluationRun
from app.schemas.results import EvaluationDashboardResponse, MetricBreakdown

logger = logging.getLogger(__name__)


def _breakdown(results: list[EvaluationResult]) -> MetricBreakdown:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total) if total > 0 else None
    return MetricBreakdown(total=total, passed=passed, failed=failed, pass_rate=pass_rate)


def build_evaluation_dashboard(run: EvaluationRun) -> EvaluationDashboardResponse:
    """Derive every dashboard metric from `run.results` (the persisted
    EvaluationResult rows), not merely by copying
    EvaluationRun.total_cases/passed_cases/failed_cases -- those stored
    columns are only cross-checked below (and a mismatch is logged, never
    silently "corrected": a GET request must never mutate data)."""
    results = run.results

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    if total != run.total_cases or passed != run.passed_cases or failed != run.failed_cases:
        logger.warning(
            "evaluation_run id=%s summary/result mismatch: stored total=%s passed=%s "
            "failed=%s vs actual (derived from results) total=%s passed=%s failed=%s",
            run.id, run.total_cases, run.passed_cases, run.failed_cases, total, passed, failed,
        )

    by_test_type = {
        test_type.value: _breakdown([r for r in results if r.test_type_snapshot == test_type])
        for test_type in TestType
    }
    by_difficulty = {
        difficulty.value: _breakdown([r for r in results if r.difficulty_snapshot == difficulty])
        for difficulty in Difficulty
    }
    by_answerability = {
        "answerable": _breakdown(
            [r for r in results if r.test_type_snapshot != TestType.UNANSWERABLE]
        ),
        "unanswerable": _breakdown(
            [r for r in results if r.test_type_snapshot == TestType.UNANSWERABLE]
        ),
    }

    return EvaluationDashboardResponse(
        evaluation_id=run.id,
        project_id=run.project_id,
        provider=run.provider,
        model_name=run.model_name,
        created_at=run.created_at,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=(passed / total) if total > 0 else None,
        by_test_type=by_test_type,
        by_difficulty=by_difficulty,
        by_answerability=by_answerability,
    )
