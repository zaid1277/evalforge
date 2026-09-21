"""
HTTP-layer tests for the M9 evaluation endpoints: status codes, request/
response shape, provider-configuration error handling. Core evaluation
logic (scoring, judging, snapshots) is covered in test_evaluation_service.py.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test in this file runs against MockProvider -- no test here
    ever calls a real LLM."""
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _create_project_with_cases(client, count=3, test_types=None, text=None, name="Eval API Test Project"):
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
    approved = [client.patch(f"/cases/{c['id']}", json={"status": "approved"}).json() for c in cases]
    return project, approved


# --- POST /projects/{id}/evaluations ---------------------------------------


def test_post_evaluation_for_missing_project_returns_404(client):
    response = client.post("/projects/999999/evaluations", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_post_evaluation_with_no_approved_cases_returns_400(client):
    project = client.post("/projects", json={"name": "Empty Project"}).json()

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    assert response.status_code == 400
    assert "No approved evaluation cases" in response.json()["detail"]


def test_post_evaluation_works(client):
    project, cases = _approved_project(client, count=3, test_types=["direct"])

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == project["id"]
    assert data["provider"] == "mock"
    assert data["model_name"] == "mock"
    assert data["total_cases"] == 3
    assert data["passed_cases"] + data["failed_cases"] == 3
    assert len(data["results"]) == 3


def test_post_evaluation_accepts_empty_body(client):
    project, cases = _approved_project(client, count=1, test_types=["direct"])

    response = client.post(f"/projects/{project['id']}/evaluations")

    assert response.status_code == 201


def test_post_evaluation_result_shape(client):
    project, cases = _approved_project(client, count=1, test_types=["direct"])

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    result = response.json()["results"][0]
    for field in (
        "evaluation_case_id", "question", "reference_answer", "model_response",
        "semantic_similarity", "passed", "evaluation_reason", "test_type", "difficulty",
    ):
        assert field in result


def test_post_evaluation_unanswerable_result_has_null_similarity(client):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    result = response.json()["results"][0]
    assert result["semantic_similarity"] is None


def test_post_evaluation_case_count_limit_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_EVALUATION_CASES", 2)
    project, cases = _approved_project(client, count=3, test_types=["direct"])

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    assert response.status_code == 400
    assert "3 approved cases" in response.json()["detail"]
    assert "limit is 2" in response.json()["detail"]


def test_post_evaluation_missing_gemini_key_fails_gracefully(client, monkeypatch):
    # Cases are generated/approved first, while still in mock mode -- only
    # the evaluation call itself needs to hit the missing-key path.
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    monkeypatch.setattr(settings, "USE_MOCK_LLM", False)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    response = client.post(f"/projects/{project['id']}/evaluations", json={})

    assert response.status_code == 500
    assert "Gemini API key is not configured" in response.json()["detail"]


# --- GET /projects/{id}/evaluations -----------------------------------------


def test_get_project_evaluations_for_missing_project_returns_404(client):
    response = client.get("/projects/999999/evaluations")

    assert response.status_code == 404


def test_get_project_evaluations_empty_list(client):
    project = client.post("/projects", json={"name": "No Runs Yet"}).json()

    response = client.get(f"/projects/{project['id']}/evaluations")

    assert response.status_code == 200
    assert response.json() == []


def test_get_project_evaluations_sorted_newest_first(client):
    project, cases = _approved_project(client, count=1, test_types=["direct"])

    first_run = client.post(f"/projects/{project['id']}/evaluations", json={}).json()
    second_run = client.post(f"/projects/{project['id']}/evaluations", json={}).json()

    listed = client.get(f"/projects/{project['id']}/evaluations").json()

    assert [r["id"] for r in listed] == [second_run["id"], first_run["id"]]


def test_get_project_evaluations_summary_fields(client):
    project, cases = _approved_project(client, count=2, test_types=["direct"])
    client.post(f"/projects/{project['id']}/evaluations", json={})

    listed = client.get(f"/projects/{project['id']}/evaluations").json()

    run = listed[0]
    for field in ("id", "provider", "model_name", "total_cases", "passed_cases", "failed_cases", "created_at"):
        assert field in run
    assert "results" not in run


def test_second_run_does_not_overwrite_first(client):
    project, cases = _approved_project(client, count=1, test_types=["direct"])

    first_run = client.post(f"/projects/{project['id']}/evaluations", json={}).json()
    second_run = client.post(f"/projects/{project['id']}/evaluations", json={}).json()

    assert first_run["id"] != second_run["id"]
    listed = client.get(f"/projects/{project['id']}/evaluations").json()
    assert len(listed) == 2


def test_evaluations_are_project_local(client):
    project_a, cases_a = _approved_project(client, count=1, text="Project A material.")
    project_b, cases_b = _approved_project(client, count=1, text="Project B material.")

    client.post(f"/projects/{project_a['id']}/evaluations", json={})
    client.post(f"/projects/{project_b['id']}/evaluations", json={})

    runs_a = client.get(f"/projects/{project_a['id']}/evaluations").json()
    runs_b = client.get(f"/projects/{project_b['id']}/evaluations").json()

    assert len(runs_a) == 1
    assert len(runs_b) == 1
    assert runs_a[0]["id"] != runs_b[0]["id"]


# --- GET /evaluations/{id} --------------------------------------------------


def test_get_single_evaluation_works(client):
    project, cases = _approved_project(client, count=2, test_types=["direct"])
    created = client.post(f"/projects/{project['id']}/evaluations", json={}).json()

    response = client.get(f"/evaluations/{created['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert len(data["results"]) == 2


def test_get_missing_evaluation_returns_404(client):
    response = client.get("/evaluations/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation run not found."


def test_get_single_evaluation_results_deterministic_order(client):
    project, cases = _approved_project(client, count=4, test_types=["direct"])
    created = client.post(f"/projects/{project['id']}/evaluations", json={}).json()

    first = client.get(f"/evaluations/{created['id']}").json()
    second = client.get(f"/evaluations/{created['id']}").json()

    assert [r["evaluation_case_id"] for r in first["results"]] == [
        r["evaluation_case_id"] for r in second["results"]
    ]


# --- GET /config/public ------------------------------------------------------


def test_public_config_reports_mock_mode(client):
    response = client.get("/config/public")

    assert response.status_code == 200
    data = response.json()
    assert data["mock_mode"] is True
    assert data["provider"] == "mock"


def test_public_config_never_exposes_api_key(client):
    response = client.get("/config/public")

    assert "GEMINI_API_KEY" not in response.text
    assert "key" not in response.json()


def test_public_config_reports_gemini_when_not_mocked(client, monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCK_LLM", False)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite")

    response = client.get("/config/public")

    data = response.json()
    assert data["mock_mode"] is False
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-3.1-flash-lite"
