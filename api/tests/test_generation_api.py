import pytest
from sqlalchemy import select

from app.config import settings
from app.models.evaluation_case import EvaluationCase
from app.providers.base import LLMProvider, ProviderResponseError
from app.schemas.generation import GenerationRequest
from app.services.generation_service import GenerationFailedError, generate_evaluation_cases


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test in this file runs against MockProvider -- no test here
    ever calls a real LLM."""
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _create_project_with_source(client, text=None):
    project = client.post("/projects", json={"name": "Handbook Project"}).json()
    text = text or (
        "Employees receive 25 days of annual leave per year.\n\n"
        "Employees with five years of service receive five extra days."
    )
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Handbook", "text": text})
    return project


class _AlwaysBadProvider(LLMProvider):
    """Test double that always returns malformed output, to exercise the
    retry-then-fail path without depending on real LLM non-determinism."""

    def __init__(self):
        self.call_count = 0

    def generate_eval_cases(self, chunks, count, difficulty, test_types):
        self.call_count += 1
        raise ProviderResponseError("simulated malformed output")

    def generate_response(self, question):
        raise NotImplementedError("not exercised by these generation-focused tests")

    def judge_unanswerable_response(self, question, model_response):
        raise NotImplementedError("not exercised by these generation-focused tests")


class _CrossProjectChunkProvider(LLMProvider):
    """Test double that returns a structurally valid case, but one that
    references a chunk id outside the project being generated for."""

    def __init__(self, bad_chunk_id: int):
        self.call_count = 0
        self.bad_chunk_id = bad_chunk_id

    def generate_eval_cases(self, chunks, count, difficulty, test_types):
        self.call_count += 1
        from app.schemas.generation import GeneratedCase

        return [
            GeneratedCase(
                question="What does the source say?",
                reference_answer="An answer.",
                source_chunk_ids=[self.bad_chunk_id],
                category="general",
                difficulty="easy",
                test_type="direct",
                is_answerable=True,
            )
        ]

    def generate_response(self, question):
        raise NotImplementedError("not exercised by these generation-focused tests")

    def judge_unanswerable_response(self, question, model_response):
        raise NotImplementedError("not exercised by these generation-focused tests")


# --- HTTP-level tests -------------------------------------------------


def test_generation_for_missing_project_returns_404(client):
    response = client.post("/projects/999999/generate", json={"count": 3})

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_generation_rejected_for_project_with_no_chunks(client):
    project = client.post("/projects", json={"name": "Empty Project"}).json()

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    assert response.status_code == 400
    assert "no source chunks" in response.json()["detail"]


def test_valid_mock_generation_persists_cases(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 4})

    assert response.status_code == 201
    data = response.json()
    assert data["generated_count"] == 4
    assert data["provider"] == "mock"
    assert data["model"] == "mock"
    assert len(data["cases"]) == 4


def test_generated_cases_start_with_generated_status(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 2})

    for case in response.json()["cases"]:
        assert case["status"] == "generated"


def test_source_chunk_associations_are_persisted(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 2})

    for case in response.json()["cases"]:
        assert len(case["source_chunk_ids"]) >= 1


def test_generation_count_limit_enforced(client):
    project = _create_project_with_source(client)

    response = client.post(
        f"/projects/{project['id']}/generate",
        json={"count": settings.MAX_GENERATION_CASES + 1},
    )

    assert response.status_code == 400
    assert "cannot exceed" in response.json()["detail"]


def test_count_zero_rejected(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 0})

    assert response.status_code == 422


def test_count_negative_rejected(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": -5})

    assert response.status_code == 422


def test_empty_test_types_selection_rejected(client):
    project = _create_project_with_source(client)

    response = client.post(
        f"/projects/{project['id']}/generate", json={"count": 3, "test_types": []}
    )

    assert response.status_code == 422


def test_list_cases_returns_persisted_cases(client):
    project = _create_project_with_source(client)
    client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    response = client.get(f"/projects/{project['id']}/cases")

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_list_cases_for_missing_project_returns_404(client):
    response = client.get("/projects/999999/cases")

    assert response.status_code == 404


def test_project_deletion_removes_evaluation_cases(client, db_session):
    project = _create_project_with_source(client)
    client.post(f"/projects/{project['id']}/generate", json={"count": 2})

    case_ids = [c["id"] for c in client.get(f"/projects/{project['id']}/cases").json()]
    assert len(case_ids) == 2

    delete_response = client.delete(f"/projects/{project['id']}")
    assert delete_response.status_code == 204

    remaining = (
        db_session.execute(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids)))
        .scalars()
        .all()
    )
    assert remaining == []


def test_unanswerable_cases_have_null_reference_answer(client):
    project = _create_project_with_source(client)

    response = client.post(
        f"/projects/{project['id']}/generate",
        json={"count": 3, "test_types": ["unanswerable"]},
    )

    cases = response.json()["cases"]
    assert len(cases) == 3
    for case in cases:
        assert case["test_type"] == "unanswerable"
        assert case["is_answerable"] is False
        assert case["reference_answer"] is None


# --- Direct service-level tests (retry / malformed-output handling) ---


def test_malformed_provider_response_does_not_persist_invalid_cases(client, db_session):
    project = _create_project_with_source(client)
    provider = _AlwaysBadProvider()

    with pytest.raises(GenerationFailedError):
        generate_evaluation_cases(
            db_session, project["id"], provider, GenerationRequest(count=3)
        )

    remaining = (
        db_session.execute(
            select(EvaluationCase).where(EvaluationCase.project_id == project["id"])
        )
        .scalars()
        .all()
    )
    assert remaining == []


def test_retry_occurs_at_most_once(client, db_session):
    project = _create_project_with_source(client)
    provider = _AlwaysBadProvider()

    with pytest.raises(GenerationFailedError):
        generate_evaluation_cases(
            db_session, project["id"], provider, GenerationRequest(count=3)
        )

    # One batch (this project has a single small source -> one batch), so
    # "at most one retry" means exactly 2 calls: the initial attempt + 1 retry.
    assert provider.call_count == 2


def test_cross_project_chunk_reference_is_rejected(client, db_session):
    project_a = _create_project_with_source(client, text="Project A source text.")
    project_b = _create_project_with_source(client, text="Project B source text.")

    # An actual chunk id belonging to project B, not project A.
    source_b_id = client.get(f"/projects/{project_b['id']}/sources").json()[0]["id"]
    chunk_b_id = client.get(f"/sources/{source_b_id}/chunks").json()[0]["id"]

    provider = _CrossProjectChunkProvider(bad_chunk_id=chunk_b_id)

    with pytest.raises(GenerationFailedError):
        generate_evaluation_cases(
            db_session, project_a["id"], provider, GenerationRequest(count=1)
        )

    assert provider.call_count == 2  # retried once, then gave up
    remaining = (
        db_session.execute(
            select(EvaluationCase).where(EvaluationCase.project_id == project_a["id"])
        )
        .scalars()
        .all()
    )
    assert remaining == []
