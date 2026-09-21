"""
Integration tests for *when* grounding scores get (re)calculated: after
generation, after a reference-answer edit, and after an answerability
change -- but not after question/category/difficulty/status-only edits.
Uses MockProvider (zero Gemini calls) and monkeypatched embeddings (zero
real-model calls).
"""

import numpy as np
import pytest

from app.config import settings
from app.services import grounding_service


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _install_fake_embeddings(monkeypatch, vectors_by_text: dict[str, list[float]]):
    def fake_embed_texts(texts):
        return np.array([vectors_by_text[text] for text in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", fake_embed_texts)


def _create_project_with_source(client, text=None):
    project = client.post("/projects", json={"name": "Grounding Integration Project"}).json()
    text = text or "Employees receive 25 days of annual leave per year."
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Doc", "text": text})
    return project


def _generate_one(client, project_id, test_type="direct"):
    return client.post(
        f"/projects/{project_id}/generate", json={"count": 1, "test_types": [test_type]}
    ).json()["cases"][0]


# --- Generation triggers grounding --------------------------------------


def test_generation_calculates_grounding_for_answerable_cases(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    cases = response.json()["cases"]
    for case in cases:
        if case["is_answerable"]:
            assert case["grounding_score"] is not None
        else:
            assert case["grounding_score"] is None


def test_generation_failure_does_not_invent_grounding_scores(client):
    project = client.post("/projects", json={"name": "No Source Project"}).json()

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    assert response.status_code == 400
    assert client.get(f"/projects/{project['id']}/cases").json() == []


# --- Edit triggers ---------------------------------------------------------


def test_reference_answer_edit_recalculates_grounding(client, monkeypatch):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")

    new_answer = "A completely different, unsupported answer."
    # The evidence text is the linked source chunk's text -- give it an
    # orthogonal vector from the new answer's, so the new score is clearly
    # different from a same-vector "no-op" result.
    source_chunk = client.get(f"/cases/{case['id']}/sources").json()[0]
    _install_fake_embeddings(
        monkeypatch,
        {
            new_answer: [0.0, 1.0],
            source_chunk["text"]: [1.0, 0.0],
        },
    )

    updated = client.patch(f"/cases/{case['id']}", json={"reference_answer": new_answer}).json()

    assert updated["reference_answer"] == new_answer
    assert updated["grounding_score"] == pytest.approx(0.0)


def test_question_only_edit_does_not_recalculate_grounding(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    baseline = case["grounding_score"]

    updated = client.patch(f"/cases/{case['id']}", json={"question": "A new question?"}).json()

    assert updated["question"] == "A new question?"
    assert updated["grounding_score"] == baseline


def test_status_only_edit_does_not_recalculate_grounding(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    baseline = case["grounding_score"]

    updated = client.patch(f"/cases/{case['id']}", json={"status": "approved"}).json()

    assert updated["status"] == "approved"
    assert updated["grounding_score"] == baseline


def test_category_only_edit_does_not_recalculate_grounding(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    baseline = case["grounding_score"]

    updated = client.patch(f"/cases/{case['id']}", json={"category": "new_category"}).json()

    assert updated["category"] == "new_category"
    assert updated["grounding_score"] == baseline


def test_difficulty_only_edit_does_not_recalculate_grounding(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    baseline = case["grounding_score"]
    new_difficulty = "medium" if case["difficulty"] == "easy" else "easy"

    updated = client.patch(f"/cases/{case['id']}", json={"difficulty": new_difficulty}).json()

    assert updated["difficulty"] == new_difficulty
    assert updated["grounding_score"] == baseline


def test_answerable_to_unanswerable_clears_grounding_score(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    assert case["grounding_score"] is not None

    updated = client.patch(f"/cases/{case['id']}", json={"test_type": "unanswerable"}).json()

    assert updated["is_answerable"] is False
    assert updated["grounding_score"] is None


def test_unanswerable_to_answerable_calculates_grounding_score(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "unanswerable")
    assert case["grounding_score"] is None

    updated = client.patch(
        f"/cases/{case['id']}",
        json={"test_type": "direct", "reference_answer": "Employees receive 25 days of leave."},
    ).json()

    assert updated["is_answerable"] is True
    assert updated["grounding_score"] is not None


def test_invalid_edit_does_not_corrupt_grounding_score(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    baseline = case["grounding_score"]

    response = client.patch(f"/cases/{case['id']}", json={"question": "   "})
    assert response.status_code == 400

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert reloaded["grounding_score"] == baseline


# --- Evidence integrity ---------------------------------------------------


def test_grounding_uses_only_linked_source_chunks(client, db_session, monkeypatch):
    from app.models.evaluation_case import EvaluationCase

    project = _create_project_with_source(
        client, text="Employees receive 25 days of annual leave per year."
    )
    case = _generate_one(client, project["id"], "direct")

    linked_chunk_text = client.get(f"/cases/{case['id']}/sources").json()[0]["text"]

    calls = []

    def spy_embed_texts(texts):
        calls.append(list(texts))
        return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", spy_embed_texts)

    # Re-run recalculation directly (via the isolated test-DB session) to
    # inspect exactly what text was embedded.
    db_case = db_session.get(EvaluationCase, case["id"])
    grounding_service.recalculate_case_grounding(db_session, db_case)

    assert calls == [[case["reference_answer"], linked_chunk_text]]


def test_unrelated_project_chunks_do_not_influence_grounding(client, db_session, monkeypatch):
    from app.models.evaluation_case import EvaluationCase

    project_a = _create_project_with_source(client, text="Project A material about leave policy.")
    _create_project_with_source(client, text="Completely unrelated project B material.")

    case_a = _generate_one(client, project_a["id"], "direct")

    calls = []

    def spy_embed_texts(texts):
        calls.append(list(texts))
        return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", spy_embed_texts)

    db_case = db_session.get(EvaluationCase, case_a["id"])
    grounding_service.recalculate_case_grounding(db_session, db_case)

    for call in calls:
        assert "Completely unrelated project B material." not in " ".join(call)


def test_unlinked_chunk_in_same_project_does_not_influence_grounding(client, db_session, monkeypatch):
    from app.models.evaluation_case import EvaluationCase

    project = _create_project_with_source(client, text="First source chunk text.")
    case = _generate_one(client, project["id"], "direct")

    # Add a second, unrelated source to the SAME project -- its chunk is
    # never linked to `case`, so it must never appear in the embedded text.
    client.post(
        f"/projects/{project['id']}/sources/text",
        json={"title": "Second Doc", "text": "An unlinked second chunk of text."},
    )

    calls = []

    def spy_embed_texts(texts):
        calls.append(list(texts))
        return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(grounding_service, "embed_texts", spy_embed_texts)

    db_case = db_session.get(EvaluationCase, case["id"])
    grounding_service.recalculate_case_grounding(db_session, db_case)

    for call in calls:
        assert "An unlinked second chunk of text." not in " ".join(call)


def test_multi_step_chunk_order_is_deterministic(client, db_session):
    from app.services.grounding_service import get_combined_evidence_text

    first_paragraph = "First fact paragraph. " + ("word " * 800)
    second_paragraph = "Second fact paragraph. " + ("word " * 800)
    project = _create_project_with_source(client, text=first_paragraph + "\n\n" + second_paragraph)

    case = _generate_one(client, project["id"], "direct")

    first = get_combined_evidence_text(db_session, case["id"])
    second = get_combined_evidence_text(db_session, case["id"])

    assert first == second  # deterministic across repeated calls


def test_linked_evidence_relationships_remain_unchanged_after_grounding(client):
    project = _create_project_with_source(client)
    case = _generate_one(client, project["id"], "direct")
    original_chunk_ids = set(case["source_chunk_ids"])

    client.patch(f"/cases/{case['id']}", json={"reference_answer": "A different but valid answer."})

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert set(reloaded["source_chunk_ids"]) == original_chunk_ids
