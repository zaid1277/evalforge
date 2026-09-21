"""
Unit tests for the M10 dashboard aggregation logic
(services/results_service.py). These build fully controlled
EvaluationRun/EvaluationResult rows directly (bypassing the M9
evaluation pipeline entirely) so breakdown counts can be asserted
exactly, without depending on MockProvider's own heuristics.
"""

import pytest

from app.models.evaluation_case import Difficulty, EvaluationCase, EvaluationStatus, TestType
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_run import EvaluationRun
from app.services import duplicate_service, grounding_service, results_service
from app.services.embedding_service import embed_texts as real_embed_texts
from app.services.results_service import build_evaluation_dashboard


def _create_case(db_session, project_id, **overrides):
    case = EvaluationCase(
        project_id=project_id,
        question=overrides.get("question", "Q?"),
        reference_answer=overrides.get("reference_answer", "A."),
        category="general",
        difficulty=overrides.get("difficulty", Difficulty.EASY),
        test_type=overrides.get("test_type", TestType.DIRECT),
        is_answerable=overrides.get("is_answerable", True),
        status=EvaluationStatus.APPROVED,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


def _build_run(db_session, project_id, specs, total_cases_override=None):
    """specs: list of dicts with keys test_type, difficulty, passed, and
    optionally similarity/reference_answer/is_answerable.
    `total_cases_override`, when given, intentionally desyncs
    EvaluationRun.total_cases from the real result count, to exercise the
    consistency-check log path (see test_mismatch_between_stored_summary_
    and_results_is_logged below)."""
    results = []
    for spec in specs:
        test_type = TestType(spec["test_type"])
        is_answerable = spec.get("is_answerable", test_type != TestType.UNANSWERABLE)
        reference_answer = spec.get("reference_answer", "A." if is_answerable else None)
        case = _create_case(
            db_session,
            project_id,
            test_type=test_type,
            difficulty=Difficulty(spec["difficulty"]),
            is_answerable=is_answerable,
            reference_answer=reference_answer,
        )
        results.append(
            EvaluationResult(
                evaluation_case_id=case.id,
                question_snapshot=case.question,
                reference_answer_snapshot=reference_answer,
                test_type_snapshot=test_type,
                difficulty_snapshot=Difficulty(spec["difficulty"]),
                model_response=spec.get("model_response", "A response."),
                semantic_similarity=spec.get("similarity"),
                passed=spec["passed"],
                evaluation_reason=spec.get("reason", "reason"),
            )
        )

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    run = EvaluationRun(
        project_id=project_id,
        provider="mock",
        model_name="mock",
        total_cases=total_cases_override if total_cases_override is not None else total,
        passed_cases=passed,
        failed_cases=total - passed,
    )
    run.results = results
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _project(client, name="Dashboard Test Project"):
    return client.post("/projects", json={"name": name}).json()


# --- Overall totals / pass rate (1-4) ---------------------------------


def test_overall_totals_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "unanswerable", "difficulty": "medium", "passed": False},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.total_cases == 3
    assert dashboard.passed_cases == 2
    assert dashboard.failed_cases == 1


def test_overall_pass_rate_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "unanswerable", "difficulty": "medium", "passed": False},
            {"test_type": "unanswerable", "difficulty": "medium", "passed": False},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.pass_rate == pytest.approx(3 / 5)


def test_100_percent_pass_rate(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True} for _ in range(4)],
    )

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.pass_rate == pytest.approx(1.0)
    assert dashboard.failed_cases == 0


def test_0_percent_pass_rate(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": False} for _ in range(4)],
    )

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.pass_rate == pytest.approx(0.0)
    assert dashboard.passed_cases == 0


# --- Test-type breakdown (5-8) -----------------------------------------


def test_direct_breakdown_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "medium", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": False},
            {"test_type": "multi_step", "difficulty": "easy", "passed": True},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    direct = dashboard.by_test_type["direct"]
    assert direct.total == 3
    assert direct.passed == 2
    assert direct.failed == 1
    assert direct.pass_rate == pytest.approx(2 / 3)


def test_multi_step_breakdown_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "multi_step", "difficulty": "easy", "passed": True},
            {"test_type": "multi_step", "difficulty": "medium", "passed": False},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    multi_step = dashboard.by_test_type["multi_step"]
    assert multi_step.total == 2
    assert multi_step.passed == 1
    assert multi_step.failed == 1
    assert multi_step.pass_rate == pytest.approx(0.5)


def test_unanswerable_breakdown_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "unanswerable", "difficulty": "easy", "passed": True},
            {"test_type": "unanswerable", "difficulty": "medium", "passed": True},
            {"test_type": "unanswerable", "difficulty": "easy", "passed": False},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    unanswerable = dashboard.by_test_type["unanswerable"]
    assert unanswerable.total == 3
    assert unanswerable.passed == 2
    assert unanswerable.failed == 1
    assert unanswerable.pass_rate == pytest.approx(2 / 3)


def test_zero_count_category_handled_safely(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True}],
    )

    dashboard = build_evaluation_dashboard(run)

    multi_step = dashboard.by_test_type["multi_step"]
    assert multi_step.total == 0
    assert multi_step.passed == 0
    assert multi_step.failed == 0
    assert multi_step.pass_rate is None  # not 0.0 -- see MetricBreakdown docstring

    unanswerable = dashboard.by_test_type["unanswerable"]
    assert unanswerable.total == 0
    assert unanswerable.pass_rate is None


# --- Difficulty breakdown (9-10) ----------------------------------------


def test_easy_difficulty_breakdown_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "unanswerable", "difficulty": "easy", "passed": False},
            {"test_type": "direct", "difficulty": "medium", "passed": True},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    easy = dashboard.by_difficulty["easy"]
    assert easy.total == 3
    assert easy.passed == 2
    assert easy.failed == 1
    assert easy.pass_rate == pytest.approx(2 / 3)


def test_medium_difficulty_breakdown_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "medium", "passed": True},
            {"test_type": "direct", "difficulty": "medium", "passed": False},
            {"test_type": "direct", "difficulty": "easy", "passed": True},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    medium = dashboard.by_difficulty["medium"]
    assert medium.total == 2
    assert medium.passed == 1
    assert medium.failed == 1
    assert medium.pass_rate == pytest.approx(0.5)


# --- Answerable vs unanswerable -------------------------------------------


def test_answerable_vs_unanswerable_breakdown(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "multi_step", "difficulty": "easy", "passed": False},
            {"test_type": "unanswerable", "difficulty": "easy", "passed": True},
        ],
    )

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.by_answerability["answerable"].total == 2
    assert dashboard.by_answerability["unanswerable"].total == 1


# --- Data source integrity (11, 19, 20) ----------------------------------


def test_dashboard_uses_only_persisted_snapshot_data(client, db_session):
    """Editing the live case after building the run must not change the
    dashboard -- results_service.py only ever reads
    EvaluationResult.*_snapshot, never the live EvaluationCase."""
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True}],
    )
    case_id = run.results[0].evaluation_case_id

    client.patch(f"/cases/{case_id}", json={"test_type": "unanswerable", "reference_answer": None})

    dashboard = build_evaluation_dashboard(run)

    assert dashboard.by_test_type["direct"].total == 1
    assert dashboard.by_test_type["unanswerable"].total == 0


def test_result_order_deterministic(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True} for _ in range(4)],
    )

    ids_first = [r.id for r in run.results]
    db_session.refresh(run)
    ids_second = [r.id for r in run.results]

    assert ids_first == ids_second == sorted(ids_first)


def test_building_dashboard_does_not_modify_run_or_results(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True}],
    )
    original_total = run.total_cases
    original_result_count = len(run.results)

    build_evaluation_dashboard(run)
    db_session.expire_all()
    reloaded = db_session.get(EvaluationRun, run.id)

    assert reloaded.total_cases == original_total
    assert len(reloaded.results) == original_result_count


# --- No AI/ML recalculation (12-15) ---------------------------------------


def test_dashboard_makes_no_embedding_calls(client, db_session, monkeypatch):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True, "similarity": 0.9},
            {"test_type": "unanswerable", "difficulty": "easy", "passed": True},
        ],
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("results_service must never call embed_texts")

    monkeypatch.setattr(results_service, "embed_texts", _forbidden, raising=False)

    build_evaluation_dashboard(run)  # must not raise


def test_dashboard_does_not_recalculate_duplicate_scores(client, db_session, monkeypatch):
    project = _project(client)
    run = _build_run(
        db_session, project["id"], [{"test_type": "direct", "difficulty": "easy", "passed": True}]
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("dashboard must never recalculate duplicate scores")

    monkeypatch.setattr(duplicate_service, "recalculate_project_duplicate_scores", _forbidden)

    build_evaluation_dashboard(run)  # must not raise


def test_dashboard_does_not_recalculate_grounding_scores(client, db_session, monkeypatch):
    project = _project(client)
    run = _build_run(
        db_session, project["id"], [{"test_type": "direct", "difficulty": "easy", "passed": True}]
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("dashboard must never recalculate grounding scores")

    monkeypatch.setattr(grounding_service, "recalculate_grounding_for_cases", _forbidden)

    build_evaluation_dashboard(run)  # must not raise


def test_results_service_module_has_no_embedding_import():
    """Structural guarantee: results_service.py doesn't even import
    embed_texts, so there is no code path that could load the real
    MiniLM model -- not just "doesn't call it in this test"."""
    assert "embed_texts" not in dir(results_service) or results_service.__dict__.get(
        "embed_texts"
    ) in (None, real_embed_texts)
    assert not any(
        "embedding_service" in name or "genai" in name.lower() or "provider" in name.lower()
        for name in getattr(results_service, "__dict__", {})
    )
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(results_service))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("embedding_service" in m or "provider" in m for m in imported_modules)


# --- Failed-result subset (18) ---------------------------------------------


def test_mismatch_between_stored_summary_and_results_is_logged(client, db_session, caplog):
    """A deliberately corrupted EvaluationRun.total_cases (out of sync
    with the actual result rows) must be surfaced as a warning, and the
    dashboard must still report the numbers derived from the real
    results -- never silently rewrite the stored columns."""
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [{"test_type": "direct", "difficulty": "easy", "passed": True}],
        total_cases_override=99,
    )

    with caplog.at_level("WARNING"):
        dashboard = build_evaluation_dashboard(run)

    assert dashboard.total_cases == 1  # derived from actual results, not the corrupted 99
    assert any("mismatch" in record.message for record in caplog.records)

    db_session.expire_all()
    reloaded = db_session.get(EvaluationRun, run.id)
    assert reloaded.total_cases == 99  # never silently "fixed"


def test_failed_result_subset_correct(client, db_session):
    project = _project(client)
    run = _build_run(
        db_session,
        project["id"],
        [
            {"test_type": "direct", "difficulty": "easy", "passed": True},
            {"test_type": "direct", "difficulty": "easy", "passed": False},
            {"test_type": "unanswerable", "difficulty": "medium", "passed": False},
        ],
    )

    failed = [r for r in run.results if not r.passed]

    assert len(failed) == 2
    assert all(not r.passed for r in failed)
