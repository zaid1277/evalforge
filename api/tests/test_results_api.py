"""
HTTP-layer tests for GET /evaluations/{id}/dashboard. Uses real mock
evaluation runs (via the M9 pipeline, MockProvider) rather than hand-built
rows -- test_results_service.py already covers exact aggregation math
with fully controlled data; this file focuses on endpoint behavior and
response shape.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _create_project_with_cases(client, count=3, test_types=None, text=None, name="Dashboard API Test"):
    project = client.post("/projects", json={"name": name}).json()
    text = text or (
        "Employees receive 25 days of annual leave per year.\n\n"
        "Employees with five years of service receive an additional five days."
    )
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Handbook", "text": text})

    payload = {"count": count}
    if test_types is not None:
        payload["test_types"] = test_types
    response = client.post(f"/projects/{project['id']}/generate", json=payload)
    return project, response.json()["cases"]


def _approved_project(client, count=3, test_types=None, text=None):
    project, cases = _create_project_with_cases(client, count=count, test_types=test_types, text=text)
    for c in cases:
        client.patch(f"/cases/{c['id']}", json={"status": "approved"})
    return project


def _run_evaluation(client, project_id):
    return client.post(f"/projects/{project_id}/evaluations", json={}).json()


def test_dashboard_endpoint_returns_200(client):
    project = _approved_project(client, count=3, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    response = client.get(f"/evaluations/{run['id']}/dashboard")

    assert response.status_code == 200


def test_dashboard_schema_correct(client):
    project = _approved_project(client, count=3, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    data = client.get(f"/evaluations/{run['id']}/dashboard").json()

    for field in (
        "evaluation_id", "project_id", "provider", "model_name", "created_at",
        "total_cases", "passed_cases", "failed_cases", "pass_rate",
        "by_test_type", "by_difficulty", "by_answerability",
    ):
        assert field in data
    for test_type in ("direct", "multi_step", "unanswerable"):
        assert test_type in data["by_test_type"]
        for field in ("total", "passed", "failed", "pass_rate"):
            assert field in data["by_test_type"][test_type]
    for difficulty in ("easy", "medium"):
        assert difficulty in data["by_difficulty"]


def test_dashboard_total_matches_run_total(client):
    project = _approved_project(client, count=5, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    assert dashboard["total_cases"] == run["total_cases"]


def test_dashboard_passed_matches_run_passed(client):
    project = _approved_project(client, count=5, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    assert dashboard["passed_cases"] == run["passed_cases"]


def test_dashboard_failed_matches_run_failed(client):
    project = _approved_project(client, count=5, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    assert dashboard["failed_cases"] == run["failed_cases"]


def test_dashboard_pass_rate_computed_correctly(client):
    project = _approved_project(client, count=5, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    expected = run["passed_cases"] / run["total_cases"]
    assert dashboard["pass_rate"] == pytest.approx(expected)


def test_dashboard_by_test_type_matches_raw_results(client):
    project = _approved_project(client, count=6, test_types=["direct", "multi_step", "unanswerable"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    for test_type in ("direct", "multi_step", "unanswerable"):
        expected_total = sum(1 for r in run["results"] if r["test_type"] == test_type)
        assert dashboard["by_test_type"][test_type]["total"] == expected_total


def test_dashboard_by_difficulty_matches_raw_results(client):
    project = _approved_project(client, count=6, test_types=["direct", "multi_step"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    for difficulty in ("easy", "medium"):
        expected_total = sum(1 for r in run["results"] if r["difficulty"] == difficulty)
        assert dashboard["by_difficulty"][difficulty]["total"] == expected_total


def test_dashboard_missing_run_returns_404(client):
    response = client.get("/evaluations/999999/dashboard")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation run not found."


def test_dashboard_exposes_no_secrets(client):
    project = _approved_project(client, count=1, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    response = client.get(f"/evaluations/{run['id']}/dashboard")

    assert "GEMINI_API_KEY" not in response.text
    assert "DATABASE_URL" not in response.text


def test_dashboard_zero_count_category_pass_rate_is_null(client):
    project = _approved_project(client, count=2, test_types=["direct"])
    run = _run_evaluation(client, project["id"])

    dashboard = client.get(f"/evaluations/{run['id']}/dashboard").json()

    assert dashboard["by_test_type"]["unanswerable"]["total"] == 0
    assert dashboard["by_test_type"]["unanswerable"]["pass_rate"] is None
