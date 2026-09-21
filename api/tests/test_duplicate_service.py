"""
Duplicate-detection logic tests. These never load the real MiniLM model --
`embed_texts` is monkeypatched with a deterministic fake so tests stay
fast and fully offline (see pytest.ini for the separate real-model test).
"""

import numpy as np
import pytest
from sqlalchemy import select

from app.models.evaluation_case import EvaluationCase
from app.services import duplicate_service


def _install_fake_embeddings(monkeypatch, vectors_by_question: dict[str, list[float]]):
    """Replace embed_texts with a lookup table + a call counter, so tests
    can assert both the resulting scores and that batching is used."""
    calls = []

    def fake_embed_texts(texts):
        calls.append(list(texts))
        return np.array([vectors_by_question[text] for text in texts])

    monkeypatch.setattr(duplicate_service, "embed_texts", fake_embed_texts)
    return calls


def _create_project(client, name="Duplicate Test Project"):
    return client.post("/projects", json={"name": name}).json()


def _create_case(db_session, project_id, question, **overrides):
    from app.models.evaluation_case import Difficulty, EvaluationStatus, TestType

    case = EvaluationCase(
        project_id=project_id,
        question=question,
        reference_answer=overrides.get("reference_answer", "An answer."),
        category=overrides.get("category", "general"),
        difficulty=overrides.get("difficulty", Difficulty.EASY),
        test_type=overrides.get("test_type", TestType.DIRECT),
        is_answerable=overrides.get("is_answerable", True),
        status=overrides.get("status", EvaluationStatus.GENERATED),
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


def test_single_case_has_null_duplicate_score(client, db_session):
    project = _create_project(client)
    case = _create_case(db_session, project["id"], "How many leave days do employees get?")

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case)
    assert case.duplicate_score is None


def test_identical_embeddings_produce_high_score(client, db_session, monkeypatch):
    project = _create_project(client)
    q1 = "How many annual leave days do employees receive?"
    q2 = "What is the employee annual leave entitlement?"
    _install_fake_embeddings(monkeypatch, {q1: [1.0, 0.0, 0.0], q2: [1.0, 0.0, 0.0]})

    case1 = _create_case(db_session, project["id"], q1)
    case2 = _create_case(db_session, project["id"], q2)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case1)
    db_session.refresh(case2)
    assert case1.duplicate_score == pytest.approx(1.0)
    assert case2.duplicate_score == pytest.approx(1.0)


def test_unrelated_embeddings_produce_low_score(client, db_session, monkeypatch):
    project = _create_project(client)
    q1 = "How many annual leave days do employees receive?"
    q2 = "What is the company policy on remote-work equipment?"
    _install_fake_embeddings(monkeypatch, {q1: [1.0, 0.0, 0.0], q2: [0.0, 1.0, 0.0]})

    case1 = _create_case(db_session, project["id"], q1)
    case2 = _create_case(db_session, project["id"], q2)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case1)
    assert case1.duplicate_score == pytest.approx(0.0)
    db_session.refresh(case2)
    assert case2.duplicate_score == pytest.approx(0.0)


def test_each_case_stores_its_highest_comparison(client, db_session, monkeypatch):
    project = _create_project(client)
    qa, qb, qc = "Question A", "Question B", "Question C"
    # A is close to B (0.94-ish) and further from C (0.6-ish).
    _install_fake_embeddings(
        monkeypatch,
        {
            qa: [1.0, 0.0],
            qb: [0.95, 0.31225],  # cos(A, B) ~ 0.95
            qc: [0.6, 0.8],  # cos(A, C) = 0.6
        },
    )
    case_a = _create_case(db_session, project["id"], qa)
    _create_case(db_session, project["id"], qb)
    _create_case(db_session, project["id"], qc)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case_a)
    assert case_a.duplicate_score == pytest.approx(0.95, abs=0.01)


def test_self_comparison_is_ignored(client, db_session, monkeypatch):
    """With only one *other* case, a case's score must come from that
    comparison, not an artificial self-match of 1.0."""
    project = _create_project(client)
    q1, q2 = "Question one", "Question two"
    _install_fake_embeddings(monkeypatch, {q1: [1.0, 0.0], q2: [0.0, 1.0]})

    case1 = _create_case(db_session, project["id"], q1)
    _create_case(db_session, project["id"], q2)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case1)
    assert case1.duplicate_score == pytest.approx(0.0)  # not 1.0 from self-comparison


def test_scores_stay_within_cosine_range(client, db_session, monkeypatch):
    project = _create_project(client)
    q1, q2, q3 = "Q1", "Q2", "Q3"
    _install_fake_embeddings(
        monkeypatch, {q1: [1.0, 0.0], q2: [-1.0, 0.0], q3: [0.0, 1.0]}
    )
    for q in (q1, q2, q3):
        _create_case(db_session, project["id"], q)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    cases = db_session.scalars(
        select(EvaluationCase).where(EvaluationCase.project_id == project["id"])
    ).all()
    for case in cases:
        assert -1.0 <= case.duplicate_score <= 1.0


def test_project_isolation(client, db_session, monkeypatch):
    project_a = _create_project(client, "Project A")
    project_b = _create_project(client, "Project B")
    identical_question = "How many leave days do employees get?"
    _install_fake_embeddings(monkeypatch, {identical_question: [1.0, 0.0]})

    case_a = _create_case(db_session, project_a["id"], identical_question)
    case_b = _create_case(db_session, project_b["id"], identical_question)

    # Only project A has been recalculated -- B has a single case, so its
    # score should still be untouched/null regardless.
    duplicate_service.recalculate_project_duplicate_scores(db_session, project_a["id"])

    db_session.refresh(case_a)
    db_session.refresh(case_b)
    assert case_a.duplicate_score is None  # only case in its project
    assert case_b.duplicate_score is None  # never touched


def test_project_isolation_with_multiple_cases_each_side(client, db_session, monkeypatch):
    project_a = _create_project(client, "Project A")
    project_b = _create_project(client, "Project B")
    qa1, qa2 = "A duplicate question", "A duplicate question restated"
    qb1, qb2 = "B duplicate question", "B duplicate question restated"
    _install_fake_embeddings(
        monkeypatch,
        {
            qa1: [1.0, 0.0],
            qa2: [1.0, 0.0],
            qb1: [0.0, 1.0],
            qb2: [0.0, 1.0],
        },
    )
    _create_case(db_session, project_a["id"], qa1)
    case_a2 = _create_case(db_session, project_a["id"], qa2)
    case_b1 = _create_case(db_session, project_b["id"], qb1)
    _create_case(db_session, project_b["id"], qb2)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project_a["id"])

    db_session.refresh(case_a2)
    db_session.refresh(case_b1)
    assert case_a2.duplicate_score == pytest.approx(1.0)
    # Project B was never recalculated, so its cases stay null.
    assert case_b1.duplicate_score is None


def test_rejected_cases_still_participate(client, db_session, monkeypatch):
    from app.models.evaluation_case import EvaluationStatus

    project = _create_project(client)
    q1, q2 = "Rejected question", "Rejected question restated"
    _install_fake_embeddings(monkeypatch, {q1: [1.0, 0.0], q2: [1.0, 0.0]})

    case1 = _create_case(db_session, project["id"], q1, status=EvaluationStatus.REJECTED)
    case2 = _create_case(db_session, project["id"], q2, status=EvaluationStatus.GENERATED)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    db_session.refresh(case1)
    db_session.refresh(case2)
    assert case1.duplicate_score == pytest.approx(1.0)
    assert case2.duplicate_score == pytest.approx(1.0)


def test_batch_embedding_is_used_not_one_call_per_question(client, db_session, monkeypatch):
    project = _create_project(client)
    questions = [f"Question {i}" for i in range(5)]
    calls = _install_fake_embeddings(
        monkeypatch, {q: [float(i), 1.0] for i, q in enumerate(questions)}
    )
    for q in questions:
        _create_case(db_session, project["id"], q)

    duplicate_service.recalculate_project_duplicate_scores(db_session, project["id"])

    assert len(calls) == 1
    assert len(calls[0]) == 5
