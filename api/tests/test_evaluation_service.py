"""
Unit/integration tests for the M9 evaluation pipeline's core logic:
DB persistence/relationships, eligibility rules, answerable scoring,
unanswerable judging, retry/atomicity behavior. HTTP-layer concerns
(status codes, request/response shape) are in test_evaluation_api.py.

Answerable-scoring tests install a monkeypatched, fully controlled
embed_texts (never the real MiniLM model) -- see test_embedding_service.py
for the one real-model smoke test, excluded from the default run.
"""

import numpy as np
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_run import EvaluationRun
from app.providers.base import JudgeResult, LLMProvider, ProviderResponseError
from app.providers.mock_provider import MockProvider
from app.services import evaluation_service
from app.services.evaluation_service import (
    EvaluationFailedError,
    EvaluationLimitExceededError,
    NoApprovedCasesError,
    evaluate_project,
)


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test in this file runs against MockProvider -- no test here
    ever calls a real LLM."""
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _install_fake_embeddings(monkeypatch, vectors_by_text: dict[str, list[float]]):
    def fake_embed_texts(texts):
        return np.array([vectors_by_text[text] for text in texts])

    monkeypatch.setattr(evaluation_service, "embed_texts", fake_embed_texts)


def _create_project_with_cases(client, count=3, test_types=None, text=None, name="Eval Test Project"):
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


def _approve_all(client, cases):
    return [client.patch(f"/cases/{c['id']}", json={"status": "approved"}).json() for c in cases]


def _approved_project(client, count=3, test_types=None, text=None):
    project, cases = _create_project_with_cases(client, count=count, test_types=test_types, text=text)
    approved = _approve_all(client, cases)
    return project, approved


class _StubProvider(LLMProvider):
    """Test double giving full control over target responses and judge
    behavior, without depending on MockProvider's own heuristics."""

    def __init__(self, response="A response.", judge_result=None, judge_error_count=0):
        self.response = response
        self.judge_result = judge_result or JudgeResult(passed=True, reason="stub pass")
        self.judge_error_count = judge_error_count
        self.judge_call_count = 0
        self.response_call_count = 0

    def generate_eval_cases(self, chunks, count, difficulty, test_types):
        raise NotImplementedError

    def generate_response(self, question):
        self.response_call_count += 1
        return self.response

    def judge_unanswerable_response(self, question, model_response):
        self.judge_call_count += 1
        if self.judge_call_count <= self.judge_error_count:
            raise ProviderResponseError("simulated malformed judge output")
        return self.judge_result


class _FailingTargetProvider(LLMProvider):
    def generate_eval_cases(self, chunks, count, difficulty, test_types):
        raise NotImplementedError

    def generate_response(self, question):
        raise ProviderResponseError("simulated target failure")

    def judge_unanswerable_response(self, question, model_response):
        raise NotImplementedError


# --- Database persistence / relationships (1-10) --------------------------


def test_evaluation_run_persists(client, db_session):
    project, cases = _approved_project(client, count=2)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    reloaded = db_session.get(EvaluationRun, run.id)
    assert reloaded is not None


def test_evaluation_result_persists(client, db_session):
    project, cases = _approved_project(client, count=2)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    results = db_session.scalars(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id)
    ).all()
    assert len(results) == 2


def test_run_belongs_to_correct_project(client, db_session):
    project, cases = _approved_project(client, count=1)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    assert run.project_id == project["id"]


def test_result_belongs_to_correct_run(client, db_session):
    project, cases = _approved_project(client, count=2)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    for result in run.results:
        assert result.evaluation_run_id == run.id


def test_result_references_correct_case(client, db_session):
    project, cases = _approved_project(client, count=2)
    case_ids = {c["id"] for c in cases}

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    result_case_ids = {r.evaluation_case_id for r in run.results}
    assert result_case_ids == case_ids


def test_project_deletion_removes_runs_and_results(client, db_session):
    project, cases = _approved_project(client, count=2)
    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")
    run_id = run.id

    delete_response = client.delete(f"/projects/{project['id']}")
    assert delete_response.status_code == 204

    # .get() would short-circuit through this session's identity map
    # (which still holds the pre-delete object) without re-querying --
    # a fresh select() is required to see the other session's DELETE.
    remaining_runs = db_session.scalars(
        select(EvaluationRun).where(EvaluationRun.id == run_id)
    ).all()
    assert remaining_runs == []
    remaining_results = db_session.scalars(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run_id)
    ).all()
    assert remaining_results == []


def test_run_deletion_removes_results(client, db_session):
    project, cases = _approved_project(client, count=2)
    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")
    run_id = run.id

    db_session.delete(db_session.get(EvaluationRun, run_id))
    db_session.commit()

    remaining_results = db_session.scalars(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run_id)
    ).all()
    assert remaining_results == []


def test_run_stores_provider(client, db_session):
    project, cases = _approved_project(client, count=1)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock-model-x")

    assert run.provider == "mock"


def test_run_stores_model(client, db_session):
    project, cases = _approved_project(client, count=1)

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock-model-x")

    assert run.model_name == "mock-model-x"


def test_summary_totals_persist_correctly(client, db_session):
    project, cases = _approved_project(client, count=3, test_types=["direct"])

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    assert run.total_cases == 3
    assert run.passed_cases + run.failed_cases == 3


# --- Eligibility (11-17, minus 404/limit-HTTP which are API-level) --------


def test_only_approved_cases_evaluated(client, db_session):
    project, cases = _create_project_with_cases(client, count=3, test_types=["direct"])
    client.patch(f"/cases/{cases[0]['id']}", json={"status": "approved"})
    client.patch(f"/cases/{cases[1]['id']}", json={"status": "rejected"})
    # cases[2] stays "generated"

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    assert run.total_cases == 1
    assert run.results[0].evaluation_case_id == cases[0]["id"]


def test_generated_cases_excluded(client, db_session):
    project, cases = _create_project_with_cases(client, count=2, test_types=["direct"])
    # Both remain "generated" -- none approved.

    with pytest.raises(NoApprovedCasesError):
        evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")


def test_rejected_cases_excluded(client, db_session):
    project, cases = _create_project_with_cases(client, count=1, test_types=["direct"])
    client.patch(f"/cases/{cases[0]['id']}", json={"status": "rejected"})

    with pytest.raises(NoApprovedCasesError):
        evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")


def test_no_approved_cases_raises_useful_error(client, db_session):
    project = client.post("/projects", json={"name": "Empty Project"}).json()

    with pytest.raises(NoApprovedCasesError, match="No approved evaluation cases"):
        evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")


def test_evaluation_limit_enforced(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_EVALUATION_CASES", 2)
    project, cases = _approved_project(client, count=3, test_types=["direct"])

    with pytest.raises(EvaluationLimitExceededError, match="3 approved cases.*limit is 2"):
        evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")


def test_another_projects_cases_never_included(client, db_session):
    project_a, cases_a = _approved_project(client, count=1, text="Project A material.")
    project_b, cases_b = _approved_project(client, count=1, text="Project B material.")

    run = evaluate_project(db_session, project_a["id"], MockProvider(), "mock", "mock")

    assert run.results[0].evaluation_case_id == cases_a[0]["id"]
    assert run.results[0].evaluation_case_id != cases_b[0]["id"]


# --- Answerable scoring (18-25) -------------------------------------------


def test_identical_response_and_reference_scores_high_and_passes(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    _install_fake_embeddings(
        monkeypatch,
        {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]},
    )
    provider = _StubProvider(response="A response.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    result = run.results[0]
    assert result.semantic_similarity == pytest.approx(1.0)
    assert result.passed is True


def test_low_similarity_response_fails(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    _install_fake_embeddings(
        monkeypatch,
        {case["reference_answer"]: [1.0, 0.0], "Unrelated.": [0.0, 1.0]},
    )
    provider = _StubProvider(response="Unrelated.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    result = run.results[0]
    assert result.semantic_similarity == pytest.approx(0.0)
    assert result.passed is False


def test_threshold_boundary_behavior(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    # Vectors chosen so cosine similarity == settings.ANSWER_SIMILARITY_THRESHOLD exactly.
    threshold = settings.ANSWER_SIMILARITY_THRESHOLD
    opposite_component = (1 - threshold**2) ** 0.5
    _install_fake_embeddings(
        monkeypatch,
        {
            case["reference_answer"]: [1.0, 0.0],
            "At threshold.": [threshold, opposite_component],
        },
    )
    provider = _StubProvider(response="At threshold.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    result = run.results[0]
    assert result.semantic_similarity == pytest.approx(threshold, abs=1e-6)
    assert result.passed is True  # ">=" threshold rule


def test_semantic_similarity_persisted(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    _install_fake_embeddings(
        monkeypatch, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]}
    )
    provider = _StubProvider(response="A response.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")
    db_session.refresh(run.results[0])

    assert run.results[0].semantic_similarity is not None


def test_evaluation_reason_populated_for_answerable(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    _install_fake_embeddings(
        monkeypatch, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]}
    )
    provider = _StubProvider(response="A response.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].evaluation_reason


def test_answerable_scoring_batches_embedding_call(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=3, test_types=["direct"])
    calls = []

    def counting_fake_embed(texts):
        calls.append(len(texts))
        return np.tile([1.0, 0.0], (len(texts), 1))

    monkeypatch.setattr(evaluation_service, "embed_texts", counting_fake_embed)
    provider = _StubProvider(response="A response.")

    evaluate_project(db_session, project["id"], provider, "mock", "mock")

    # One batched call covering all 3 reference answers + 3 responses,
    # not 3 separate calls.
    assert calls == [6]


def test_evaluation_does_not_modify_duplicate_score(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=2, test_types=["direct"])
    before = {c["id"]: c["duplicate_score"] for c in client.get(f"/projects/{project['id']}/cases").json()}
    _install_fake_embeddings(
        monkeypatch,
        {c["reference_answer"]: [1.0, 0.0] for c in cases} | {"A response.": [1.0, 0.0]},
    )
    provider = _StubProvider(response="A response.")

    evaluate_project(db_session, project["id"], provider, "mock", "mock")

    after = {c["id"]: c["duplicate_score"] for c in client.get(f"/projects/{project['id']}/cases").json()}
    assert after == before


def test_evaluation_does_not_modify_grounding_score(client, db_session, monkeypatch):
    project, cases = _approved_project(client, count=2, test_types=["direct"])
    before = {c["id"]: c["grounding_score"] for c in client.get(f"/projects/{project['id']}/cases").json()}
    _install_fake_embeddings(
        monkeypatch,
        {c["reference_answer"]: [1.0, 0.0] for c in cases} | {"A response.": [1.0, 0.0]},
    )
    provider = _StubProvider(response="A response.")

    evaluate_project(db_session, project["id"], provider, "mock", "mock")

    after = {c["id"]: c["grounding_score"] for c in client.get(f"/projects/{project['id']}/cases").json()}
    assert after == before


# --- Unanswerable judging (26-32) ------------------------------------------


def test_refusal_style_response_passes(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(
        response="I don't know.", judge_result=JudgeResult(passed=True, reason="acknowledges gap")
    )

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].passed is True
    assert run.results[0].semantic_similarity is None


def test_fabricated_response_fails(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(
        response="The answer is 42.", judge_result=JudgeResult(passed=False, reason="invented info")
    )

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].passed is False


def test_unanswerable_semantic_similarity_is_null(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(response="I don't know.")

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].semantic_similarity is None


def test_unanswerable_reason_persisted(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(
        response="I don't know.", judge_result=JudgeResult(passed=True, reason="a specific reason")
    )

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].evaluation_reason == "a specific reason"


def test_judge_structured_output_validated_via_mock_provider(client, db_session):
    """MockProvider's judge is the deterministic stand-in exercised by
    every other test here -- this just confirms it returns a real
    JudgeResult (passed: bool, reason: str), matching the shape Gemini's
    validated JudgeVerdict produces."""
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    result = run.results[0]
    assert isinstance(result.passed, bool)
    assert isinstance(result.evaluation_reason, str) and result.evaluation_reason


def test_malformed_judge_output_retries_at_most_once_then_succeeds(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(
        response="I don't know.",
        judge_result=JudgeResult(passed=True, reason="recovered"),
        judge_error_count=1,
    )

    run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert provider.judge_call_count == 2  # initial attempt + 1 retry
    assert run.results[0].passed is True


def test_malformed_judge_failure_does_not_create_corrupted_run(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["unanswerable"])
    provider = _StubProvider(response="I don't know.", judge_error_count=99)  # always fails

    with pytest.raises(EvaluationFailedError):
        evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert provider.judge_call_count == 2  # initial attempt + 1 retry, then gave up

    remaining_runs = db_session.scalars(
        select(EvaluationRun).where(EvaluationRun.project_id == project["id"])
    ).all()
    assert remaining_runs == []


# --- Provider-input safety (36-37) -----------------------------------------


def test_target_model_receives_only_the_question(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]

    received = {}

    class _RecordingProvider(_StubProvider):
        def generate_response(self, question):
            received["question"] = question
            return super().generate_response(question)

    provider = _RecordingProvider(response="A response.")
    with pytest.MonkeyPatch.context() as mp:
        _install_fake_embeddings(mp, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]})
        evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert received["question"] == case["question"]
    assert case["reference_answer"] not in received["question"]


# --- Atomicity: target-response failure aborts before any DB write --------


def test_target_response_failure_persists_nothing(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])

    with pytest.raises(EvaluationFailedError):
        evaluate_project(db_session, project["id"], _FailingTargetProvider(), "mock", "mock")

    remaining_runs = db_session.scalars(
        select(EvaluationRun).where(EvaluationRun.project_id == project["id"])
    ).all()
    assert remaining_runs == []


# --- Snapshot integrity (39-42) --------------------------------------------


def test_question_snapshot_stored(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    provider = _StubProvider(response="A response.")

    with pytest.MonkeyPatch.context() as mp:
        _install_fake_embeddings(mp, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]})
        run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].question_snapshot == case["question"]


def test_reference_answer_snapshot_stored(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    provider = _StubProvider(response="A response.")

    with pytest.MonkeyPatch.context() as mp:
        _install_fake_embeddings(mp, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]})
        run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    assert run.results[0].reference_answer_snapshot == case["reference_answer"]


def test_editing_case_after_evaluation_does_not_change_historical_result(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    original_question = case["question"]
    original_reference_answer = case["reference_answer"]
    provider = _StubProvider(response="A response.")

    with pytest.MonkeyPatch.context() as mp:
        _install_fake_embeddings(mp, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]})
        run = evaluate_project(db_session, project["id"], provider, "mock", "mock")
    run_id = run.id

    client.patch(
        f"/cases/{case['id']}",
        json={"question": "A totally different question?", "reference_answer": "A totally different answer."},
    )

    reloaded_run = db_session.get(EvaluationRun, run_id)
    db_session.refresh(reloaded_run)
    result = reloaded_run.results[0]
    assert result.question_snapshot == original_question
    assert result.reference_answer_snapshot == original_reference_answer


def test_test_type_and_difficulty_snapshot_preserved(client, db_session):
    project, cases = _approved_project(client, count=1, test_types=["direct"])
    case = cases[0]
    provider = _StubProvider(response="A response.")

    with pytest.MonkeyPatch.context() as mp:
        _install_fake_embeddings(mp, {case["reference_answer"]: [1.0, 0.0], "A response.": [1.0, 0.0]})
        run = evaluate_project(db_session, project["id"], provider, "mock", "mock")

    result = run.results[0]
    assert result.test_type_snapshot.value == case["test_type"]
    assert result.difficulty_snapshot.value == case["difficulty"]


# --- Deterministic ordering -------------------------------------------------


def test_results_ordered_by_case_id_ascending(client, db_session):
    project, cases = _approved_project(client, count=4, test_types=["direct"])

    run = evaluate_project(db_session, project["id"], MockProvider(), "mock", "mock")

    case_ids = [r.evaluation_case_id for r in run.results]
    assert case_ids == sorted(case_ids)


# --- Real MiniLM smoke test (excluded by default -- see pytest.ini) -------


@pytest.mark.real_model
def test_real_minilm_answer_scoring():
    """One real, non-mocked run of all-MiniLM-L6-v2 for answer scoring
    (see PRD M9 'Real MiniLM Verification'). No API key involved.

    Calls embedding_service.embed_texts/cosine_similarity directly rather
    than going through evaluation_service -- conftest.py's autouse
    fixture monkeypatches the `embed_texts` name *inside*
    evaluation_service for every other test in the suite, so going
    through that module here would silently use the fake instead of the
    real model (the same trap noted in test_grounding_service.py).
    """
    from app.services.embedding_service import cosine_similarity, embed_texts

    reference = "Employees receive 25 days of annual leave each year."
    similar = "Employees are entitled to 25 annual leave days per year."
    unrelated = "Employees receive a company laptop."
    wrong_number = "Employees receive 20 days of annual leave each year."

    vectors = embed_texts([reference, similar, unrelated, wrong_number])
    sim_similar = cosine_similarity(vectors[0], vectors[1])
    sim_unrelated = cosine_similarity(vectors[0], vectors[2])
    sim_wrong_number = cosine_similarity(vectors[0], vectors[3])

    print(f"\nsimilarity(reference, similar) = {sim_similar:.4f}")
    print(f"similarity(reference, unrelated) = {sim_unrelated:.4f}")
    print(f"similarity(reference, wrong_number) = {sim_wrong_number:.4f}")

    assert sim_similar > sim_unrelated
    # Known limitation, reported rather than hidden (see
    # ANSWER_SIMILARITY_THRESHOLD's comment in app/config.py): a
    # same-topic wrong-fact answer can still score higher than an
    # unrelated one, since embedding similarity captures topical
    # relatedness, not fact-checking.
    assert sim_wrong_number > sim_unrelated
