"""
Integration tests for *when* duplicate scores get (re)calculated: after
generation, and after a question edit -- but not after other kinds of
edits. Uses MockProvider (zero Gemini calls) and a monkeypatched
embed_texts (zero real-model calls), so these stay fast and offline.
"""

import numpy as np
import pytest

from app.config import settings
from app.services import duplicate_service

# conftest.py's `_no_real_embedding_model_by_default` autouse fixture already
# replaces embed_texts with a fast deterministic fake (identical text ->
# identical vector) for every test in the suite. These tests only need to
# override it locally where they want *precise* control over similarity
# scores between specific, non-identical questions.


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _install_fake_embeddings(monkeypatch, vectors_by_question: dict[str, list[float]]):
    """Precise, per-test override of the autouse hash-based fake, for
    tests that need to control exact similarity values."""

    def fake_embed_texts(texts):
        return np.array([vectors_by_question[text] for text in texts])

    monkeypatch.setattr(duplicate_service, "embed_texts", fake_embed_texts)


def _create_project_with_source(client, text=None):
    project = client.post("/projects", json={"name": "Dup Integration Project"}).json()
    text = text or "Employees receive 25 days of annual leave per year."
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Doc", "text": text})
    return project


def _generate_one(client, project_id, test_type="direct"):
    return client.post(
        f"/projects/{project_id}/generate", json={"count": 1, "test_types": [test_type]}
    ).json()["cases"][0]


# --- Generation integration -------------------------------------------


def test_generation_triggers_duplicate_recalculation(client):
    project = _create_project_with_source(client)

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    cases = response.json()["cases"]
    assert all(c["duplicate_score"] is not None for c in cases)


def test_newly_generated_duplicate_case_gets_flagged(client):
    project = _create_project_with_source(client)

    # MockProvider is deterministic: generating with the same params
    # against the same single source chunk twice produces identical
    # question text both times.
    first = _generate_one(client, project["id"])
    second = _generate_one(client, project["id"])

    assert first["question"] == second["question"]
    assert second["duplicate_score"] == pytest.approx(1.0)
    assert second["is_possible_duplicate"] is True


def test_pre_existing_case_also_updated_after_new_duplicate_appears(client):
    project = _create_project_with_source(client)

    first = _generate_one(client, project["id"])
    assert first["duplicate_score"] is None  # only case in the project so far

    _generate_one(client, project["id"])

    refreshed_first = client.get(f"/cases/{first['id']}").json()
    assert refreshed_first["duplicate_score"] == pytest.approx(1.0)


def test_duplicate_score_persists(client):
    project = _create_project_with_source(client)
    _generate_one(client, project["id"])
    second = _generate_one(client, project["id"])

    reloaded = client.get(f"/cases/{second['id']}").json()
    assert reloaded["duplicate_score"] == pytest.approx(1.0)


def test_generation_failure_does_not_invent_duplicate_scores(client):
    project = client.post("/projects", json={"name": "No Source Project"}).json()

    response = client.post(f"/projects/{project['id']}/generate", json={"count": 3})

    assert response.status_code == 400  # no chunks available to generate from
    assert client.get(f"/projects/{project['id']}/cases").json() == []


# --- Review/edit integration -------------------------------------------


def test_editing_question_triggers_recalculation(client, monkeypatch):
    project = _create_project_with_source(client)
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "unanswerable")

    new_question = "An edited, now-distinct question about payroll timing."
    _install_fake_embeddings(
        monkeypatch,
        {
            case_a["question"]: [1.0, 0.0],
            new_question: [0.0, 1.0],
        },
    )

    updated = client.patch(f"/cases/{case_b['id']}", json={"question": new_question}).json()

    assert updated["question"] == new_question
    assert updated["duplicate_score"] == pytest.approx(0.0)


def test_editing_reference_answer_does_not_recalculate(client, monkeypatch):
    project = _create_project_with_source(client)
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "direct")
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [0.0, 1.0]}
    )
    baseline = client.get(f"/cases/{case_b['id']}").json()["duplicate_score"]

    # Swap in embeddings that would produce a *different* score if the
    # recalculation ran again -- if it doesn't run, the score won't move.
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [1.0, 0.0]}
    )

    updated = client.patch(f"/cases/{case_b['id']}", json={"reference_answer": "A new answer."}).json()

    assert updated["duplicate_score"] == pytest.approx(baseline)


def test_status_only_change_does_not_recalculate(client, monkeypatch):
    project = _create_project_with_source(client)
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "direct")
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [0.0, 1.0]}
    )
    baseline = client.get(f"/cases/{case_b['id']}").json()["duplicate_score"]

    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [1.0, 0.0]}
    )

    updated = client.patch(f"/cases/{case_b['id']}", json={"status": "approved"}).json()

    assert updated["status"] == "approved"
    assert updated["duplicate_score"] == pytest.approx(baseline)


def test_changed_question_can_remove_duplicate_warning(client, monkeypatch):
    project = _create_project_with_source(client)
    # Both generated with the same params against the same single source
    # chunk -- MockProvider deterministically gives them identical
    # question text, so they start out flagged as duplicates of each other.
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "direct")
    assert case_a["question"] == case_b["question"]

    before = client.get(f"/cases/{case_b['id']}").json()
    assert before["is_possible_duplicate"] is True

    new_question = "A totally different, unrelated question about office locations."
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], new_question: [0.0, 1.0]}
    )
    after = client.patch(f"/cases/{case_b['id']}", json={"question": new_question}).json()

    assert after["is_possible_duplicate"] is False
    assert after["duplicate_score"] == pytest.approx(0.0)


def test_changed_question_can_create_duplicate_warning(client, monkeypatch):
    project = _create_project_with_source(client)
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "unanswerable")
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [0.0, 1.0]}
    )

    before = client.get(f"/cases/{case_b['id']}").json()
    assert before["is_possible_duplicate"] is False

    _install_fake_embeddings(monkeypatch, {case_a["question"]: [1.0, 0.0]})
    after = client.patch(f"/cases/{case_b['id']}", json={"question": case_a["question"]}).json()

    assert after["duplicate_score"] == pytest.approx(1.0)
    assert after["is_possible_duplicate"] is True


def test_invalid_edit_does_not_alter_duplicate_scores(client, monkeypatch):
    project = _create_project_with_source(client)
    case_a = _generate_one(client, project["id"], "direct")
    case_b = _generate_one(client, project["id"], "direct")
    _install_fake_embeddings(
        monkeypatch, {case_a["question"]: [1.0, 0.0], case_b["question"]: [0.0, 1.0]}
    )
    before = client.get(f"/cases/{case_b['id']}").json()["duplicate_score"]

    response = client.patch(f"/cases/{case_b['id']}", json={"question": "   "})
    assert response.status_code == 400

    after = client.get(f"/cases/{case_b['id']}").json()["duplicate_score"]
    assert after == pytest.approx(before)
