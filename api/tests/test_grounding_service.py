"""
Unit tests for the grounding heuristic's core logic. These use a
monkeypatched embed_texts (deterministic fake vectors), never the real
MiniLM model -- see test_embedding_service.py for the one real-model
smoke test, excluded from the default run (pytest.ini).
"""

import numpy as np
import pytest

from app.config import settings
from app.models.evaluation_case import Difficulty, EvaluationCase, TestType
from app.models.evaluation_case_source import EvaluationCaseSource
from app.services import grounding_service


def _install_fake_embeddings(monkeypatch, vectors_by_text: dict[str, list[float]]):
    def fake_embed_texts(texts):
        return np.array([vectors_by_text[text] for text in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", fake_embed_texts)


def _create_project_with_chunks(client, texts):
    """Create a project with one source made of the given paragraphs, and
    return (project, list_of_chunk_dicts) in document order."""
    project = client.post("/projects", json={"name": "Grounding Test Project"}).json()
    source = client.post(
        f"/projects/{project['id']}/sources/text",
        json={"title": "Doc", "text": "\n\n".join(texts)},
    ).json()
    chunks = client.get(f"/sources/{source['id']}/chunks").json()
    return project, chunks


def _create_case(db_session, project_id, chunk_ids, **overrides):
    case = EvaluationCase(
        project_id=project_id,
        question=overrides.get("question", "What does the source say?"),
        reference_answer=overrides.get("reference_answer", "An answer."),
        category=overrides.get("category", "general"),
        difficulty=overrides.get("difficulty", Difficulty.EASY),
        test_type=overrides.get("test_type", TestType.DIRECT),
        is_answerable=overrides.get("is_answerable", True),
    )
    case.source_links = [EvaluationCaseSource(source_chunk_id=cid) for cid in chunk_ids]
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


# --- Core similarity behavior ------------------------------------------


def test_related_texts_score_higher_than_unrelated(monkeypatch):
    _install_fake_embeddings(
        monkeypatch,
        {
            "answer": [1.0, 0.0],
            "related evidence": [0.95, 0.31225],
            "unrelated evidence": [0.0, 1.0],
        },
    )

    related = grounding_service.calculate_grounding_score("answer", "related evidence")
    unrelated = grounding_service.calculate_grounding_score("answer", "unrelated evidence")

    assert related > unrelated


def test_unrelated_texts_score_near_zero(monkeypatch):
    _install_fake_embeddings(monkeypatch, {"answer": [1.0, 0.0], "evidence": [0.0, 1.0]})

    score = grounding_service.calculate_grounding_score("answer", "evidence")

    assert score == pytest.approx(0.0)


def test_zero_vector_does_not_crash(monkeypatch):
    _install_fake_embeddings(monkeypatch, {"answer": [0.0, 0.0], "evidence": [1.0, 0.0]})

    score = grounding_service.calculate_grounding_score("answer", "evidence")

    assert score == 0.0


# --- Case-level recalculation --------------------------------------------


def test_answerable_single_chunk_case_gets_score(client, db_session, monkeypatch):
    project, chunks = _create_project_with_chunks(client, ["Employees receive 25 days of leave."])
    case = _create_case(
        db_session,
        project["id"],
        [chunks[0]["id"]],
        reference_answer="Employees receive 25 days of leave.",
    )
    _install_fake_embeddings(
        monkeypatch,
        {
            "Employees receive 25 days of leave.": [1.0, 0.0],
        },
    )

    score = grounding_service.recalculate_case_grounding(db_session, case)

    assert score == pytest.approx(1.0)
    db_session.refresh(case)
    assert case.grounding_score == pytest.approx(1.0)


def test_multi_step_case_combines_both_evidence_chunks(client, db_session, monkeypatch):
    # Each paragraph must be large enough on its own to become its own
    # chunk (see chunking_service.py's ~750-word target) -- two short
    # paragraphs would otherwise be merged into a single chunk.
    first_paragraph = "First fact paragraph. " + ("word " * 800)
    second_paragraph = "Second fact paragraph. " + ("word " * 800)
    project, chunks = _create_project_with_chunks(client, [first_paragraph, second_paragraph])
    assert len(chunks) == 2

    chunk_ids = [chunks[0]["id"], chunks[1]["id"]]
    case = _create_case(
        db_session,
        project["id"],
        chunk_ids,
        test_type=TestType.MULTI_STEP,
        reference_answer="Combined answer.",
    )
    combined_text = f"{chunks[0]['text']}\n\n{chunks[1]['text']}"

    calls = []

    def fake_embed_texts(texts):
        calls.append(list(texts))
        return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", fake_embed_texts)

    grounding_service.recalculate_case_grounding(db_session, case)

    assert calls == [["Combined answer.", combined_text]]


def test_unanswerable_case_gets_null_score(client, db_session):
    project, chunks = _create_project_with_chunks(client, ["Some source text."])
    case = _create_case(
        db_session,
        project["id"],
        [chunks[0]["id"]],
        test_type=TestType.UNANSWERABLE,
        is_answerable=False,
        reference_answer=None,
    )

    score = grounding_service.recalculate_case_grounding(db_session, case)

    assert score is None
    db_session.refresh(case)
    assert case.grounding_score is None


def test_answerable_case_with_no_linked_evidence_handled_safely(db_session):
    from app.models.project import Project

    project = Project(name="No Evidence Project")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    case = EvaluationCase(
        project_id=project.id,
        question="Q?",
        reference_answer="An answer with no linked chunks.",
        category="general",
        difficulty=Difficulty.EASY,
        test_type=TestType.DIRECT,
        is_answerable=True,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    score = grounding_service.recalculate_case_grounding(db_session, case)

    assert score is None
    db_session.refresh(case)
    assert case.grounding_score is None


def test_score_persists_across_reload(client, db_session, monkeypatch):
    project, chunks = _create_project_with_chunks(client, ["Employees receive 25 days of leave."])
    case = _create_case(
        db_session,
        project["id"],
        [chunks[0]["id"]],
        reference_answer="Employees receive 25 days of leave.",
    )
    _install_fake_embeddings(monkeypatch, {"Employees receive 25 days of leave.": [1.0, 0.0]})

    grounding_service.recalculate_case_grounding(db_session, case)
    case_id = case.id

    reloaded = db_session.get(EvaluationCase, case_id)
    assert reloaded.grounding_score == pytest.approx(1.0)


# --- Threshold / review-flag behavior (schema-level) ---------------------


def _response_dict(case):
    from app.schemas.evaluation_case import EvaluationCaseResponse

    return EvaluationCaseResponse.model_validate(case).model_dump()


def test_threshold_comparison_and_flag_below(client, db_session, monkeypatch):
    project, chunks = _create_project_with_chunks(client, ["Employees receive 25 days of leave."])
    case = _create_case(
        db_session,
        project["id"],
        [chunks[0]["id"]],
        reference_answer="Employees receive a company car.",
    )
    _install_fake_embeddings(
        monkeypatch,
        {"Employees receive a company car.": [1.0, 0.0], "Employees receive 25 days of leave.": [0.0, 1.0]},
    )
    grounding_service.recalculate_case_grounding(db_session, case)

    data = _response_dict(case)
    assert data["grounding_score"] < settings.GROUNDING_SIMILARITY_THRESHOLD
    assert data["needs_grounding_review"] is True


def test_threshold_comparison_and_flag_above(client, db_session, monkeypatch):
    project, chunks = _create_project_with_chunks(client, ["Employees receive 25 days of leave."])
    case = _create_case(
        db_session,
        project["id"],
        [chunks[0]["id"]],
        reference_answer="Employees receive 25 days of leave.",
    )
    _install_fake_embeddings(monkeypatch, {"Employees receive 25 days of leave.": [1.0, 0.0]})
    grounding_service.recalculate_case_grounding(db_session, case)

    data = _response_dict(case)
    assert data["grounding_score"] >= settings.GROUNDING_SIMILARITY_THRESHOLD
    assert data["needs_grounding_review"] is False


# --- Real MiniLM smoke test (excluded by default -- see pytest.ini) -----


@pytest.mark.real_model
def test_real_minilm_related_answer_scores_higher_than_unrelated():
    """One real, non-mocked run of all-MiniLM-L6-v2 for grounding (see PRD
    M7 'Real MiniLM Verification'). No API key involved.

    Calls embedding_service.embed_texts/cosine_similarity directly rather
    than going through grounding_service.calculate_grounding_score --
    conftest.py's autouse fixture monkeypatches the `embed_texts` name
    *inside* grounding_service for every other test in the suite, so
    going through that module here would silently use the fake instead
    of the real model.
    """
    from app.services.embedding_service import cosine_similarity, embed_texts

    reference_answer = "Employees receive 25 days of annual leave per year."
    related_evidence = (
        "All full-time employees are entitled to 25 days of annual leave each calendar year."
    )
    unrelated_evidence = "Remote employees may request a company laptop and monitor."

    vectors = embed_texts([reference_answer, related_evidence, unrelated_evidence])
    related_score = cosine_similarity(vectors[0], vectors[1])
    unrelated_score = cosine_similarity(vectors[0], vectors[2])

    print(f"\nsimilarity(related) = {related_score:.4f}")
    print(f"similarity(unrelated) = {unrelated_score:.4f}")

    assert related_score > unrelated_score
