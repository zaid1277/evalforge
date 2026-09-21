import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test in this file runs against MockProvider -- no test here
    ever calls a real LLM."""
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _create_project_with_cases(client, count=5, test_types=None, text=None):
    project = client.post("/projects", json={"name": "Review Test Project"}).json()
    text = text or (
        "Employees receive 25 days of annual leave per year.\n\n"
        "Employees with five years of service receive an additional five days."
    )
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Handbook", "text": text})

    payload = {"count": count}
    if test_types is not None:
        payload["test_types"] = test_types
    response = client.post(f"/projects/{project['id']}/generate", json=payload)
    cases = response.json()["cases"]
    return project, cases


def _direct_case(client):
    _, cases = _create_project_with_cases(client, count=1, test_types=["direct"])
    return cases[0]


def _unanswerable_case(client):
    _, cases = _create_project_with_cases(client, count=1, test_types=["unanswerable"])
    return cases[0]


def _multi_step_case(client):
    # A single short source only ever yields one chunk, so ask for a
    # slightly longer one to guarantee at least two chunks exist for a
    # genuine multi_step case.
    long_text = "\n\n".join(f"Paragraph {i}. " + ("word " * 800) for i in range(3))
    _, cases = _create_project_with_cases(
        client, count=1, test_types=["multi_step"], text=long_text
    )
    return cases[0]


# --- PATCH tests --------------------------------------------------------


def test_update_question(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"question": "Updated question?"})

    assert response.status_code == 200
    assert response.json()["question"] == "Updated question?"


def test_update_reference_answer(client):
    case = _direct_case(client)

    response = client.patch(
        f"/cases/{case['id']}", json={"reference_answer": "Updated reference answer."}
    )

    assert response.status_code == 200
    assert response.json()["reference_answer"] == "Updated reference answer."


def test_update_category(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"category": "leave_policy"})

    assert response.status_code == 200
    assert response.json()["category"] == "leave_policy"


def test_update_difficulty(client):
    case = _direct_case(client)
    new_difficulty = "medium" if case["difficulty"] == "easy" else "easy"

    response = client.patch(f"/cases/{case['id']}", json={"difficulty": new_difficulty})

    assert response.status_code == 200
    assert response.json()["difficulty"] == new_difficulty


def test_update_test_type_direct_to_multi_step(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"test_type": "multi_step"})

    assert response.status_code == 200
    assert response.json()["test_type"] == "multi_step"
    assert response.json()["is_answerable"] is True


def test_approve_generated_case(client):
    case = _direct_case(client)
    assert case["status"] == "generated"

    response = client.patch(f"/cases/{case['id']}", json={"status": "approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_reject_generated_case(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"status": "rejected"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_approved_to_rejected(client):
    case = _direct_case(client)
    client.patch(f"/cases/{case['id']}", json={"status": "approved"})

    response = client.patch(f"/cases/{case['id']}", json={"status": "rejected"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_rejected_to_approved(client):
    case = _direct_case(client)
    client.patch(f"/cases/{case['id']}", json={"status": "rejected"})

    response = client.patch(f"/cases/{case['id']}", json={"status": "approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_update_nonexistent_case_returns_404(client):
    response = client.patch("/cases/999999", json={"status": "approved"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation case not found."


# --- Validation tests ----------------------------------------------------


def test_reject_empty_question(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"question": ""})

    assert response.status_code == 400


def test_reject_whitespace_only_question(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"question": "   "})

    assert response.status_code == 400


def test_reject_empty_category(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"category": ""})

    assert response.status_code == 400


def test_reject_invalid_difficulty(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"difficulty": "hard"})

    assert response.status_code == 422


def test_reject_invalid_test_type(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"test_type": "open_ended"})

    assert response.status_code == 422


def test_answerable_case_with_empty_answer_rejected(client):
    case = _direct_case(client)
    assert case["is_answerable"] is True

    response = client.patch(f"/cases/{case['id']}", json={"reference_answer": ""})

    assert response.status_code == 400


def test_unanswerable_case_with_answer_rejected(client):
    case = _unanswerable_case(client)
    assert case["is_answerable"] is False

    response = client.patch(
        f"/cases/{case['id']}", json={"reference_answer": "A fabricated answer."}
    )

    assert response.status_code == 400


def test_unanswerable_with_is_answerable_true_rejected(client):
    case = _unanswerable_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"is_answerable": True})

    assert response.status_code == 400


def test_switching_test_type_to_unanswerable_normalizes_answerability(client):
    case = _direct_case(client)

    response = client.patch(f"/cases/{case['id']}", json={"test_type": "unanswerable"})

    assert response.status_code == 200
    data = response.json()
    assert data["test_type"] == "unanswerable"
    assert data["is_answerable"] is False
    assert data["reference_answer"] is None


def test_partial_patch_validates_resulting_complete_object(client):
    case = _direct_case(client)
    assert case["is_answerable"] is True
    assert case["reference_answer"]

    # Clearing the reference answer alone makes the *whole* case invalid,
    # even though the PATCH body only touches one field.
    response = client.patch(f"/cases/{case['id']}", json={"reference_answer": ""})

    assert response.status_code == 400


def test_invalid_patch_does_not_alter_persisted_row(client):
    case = _direct_case(client)
    original_question = case["question"]

    response = client.patch(f"/cases/{case['id']}", json={"question": "   "})
    assert response.status_code == 400

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert reloaded["question"] == original_question


# --- Evidence tests --------------------------------------------------------


def test_case_evidence_returns_only_linked_chunks(client):
    case = _direct_case(client)

    response = client.get(f"/cases/{case['id']}/sources")

    assert response.status_code == 200
    chunks = response.json()
    assert len(chunks) >= 1
    assert {c["id"] for c in chunks} == set(case["source_chunk_ids"])
    assert chunks[0]["source_filename"] == "Handbook"


def test_evidence_chunks_returned_in_deterministic_order(client):
    case = _multi_step_case(client)

    first = client.get(f"/cases/{case['id']}/sources").json()
    second = client.get(f"/cases/{case['id']}/sources").json()

    assert [c["id"] for c in first] == [c["id"] for c in second]
    ids = [c["id"] for c in first]
    assert ids == sorted(ids)


def test_evidence_for_nonexistent_case_returns_404(client):
    response = client.get("/cases/999999/sources")

    assert response.status_code == 404


def test_multi_step_case_can_return_two_evidence_chunks(client):
    case = _multi_step_case(client)

    response = client.get(f"/cases/{case['id']}/sources")

    assert response.status_code == 200
    assert len(response.json()) == len(case["source_chunk_ids"])
    assert len(case["source_chunk_ids"]) <= 2


def test_evidence_excludes_chunks_from_other_projects(client):
    project_a, cases_a = _create_project_with_cases(client, count=1, text="Project A material.")
    project_b, _ = _create_project_with_cases(client, count=1, text="Completely unrelated project B material.")

    case_a = cases_a[0]
    evidence = client.get(f"/cases/{case_a['id']}/sources").json()

    project_b_sources = client.get(f"/projects/{project_b['id']}/sources").json()
    project_b_chunk_ids = set()
    for source in project_b_sources:
        for chunk in client.get(f"/sources/{source['id']}/chunks").json():
            project_b_chunk_ids.add(chunk["id"])

    evidence_ids = {c["id"] for c in evidence}
    assert evidence_ids.isdisjoint(project_b_chunk_ids)


# --- Persistence tests ------------------------------------------------


def test_updated_status_persists(client):
    case = _direct_case(client)
    client.patch(f"/cases/{case['id']}", json={"status": "approved"})

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert reloaded["status"] == "approved"


def test_edited_question_persists(client):
    case = _direct_case(client)
    client.patch(f"/cases/{case['id']}", json={"question": "A durable edit."})

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert reloaded["question"] == "A durable edit."


def test_approved_case_remains_approved_in_project_list(client):
    project, cases = _create_project_with_cases(client, count=1)
    case = cases[0]
    client.patch(f"/cases/{case['id']}", json={"status": "approved"})

    listed = client.get(f"/projects/{project['id']}/cases").json()
    assert listed[0]["status"] == "approved"


def test_rejection_does_not_delete_case(client):
    case = _direct_case(client)
    client.patch(f"/cases/{case['id']}", json={"status": "rejected"})

    response = client.get(f"/cases/{case['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_editing_does_not_modify_source_chunk_relationships(client):
    case = _direct_case(client)
    original_chunk_ids = set(case["source_chunk_ids"])

    client.patch(
        f"/cases/{case['id']}",
        json={"question": "New question", "reference_answer": "New answer", "category": "x"},
    )

    reloaded = client.get(f"/cases/{case['id']}").json()
    assert set(reloaded["source_chunk_ids"]) == original_chunk_ids


# --- M6: duplicate-score fields in API responses ------------------------


def test_case_response_includes_duplicate_score_field(client):
    case = _direct_case(client)
    assert "duplicate_score" in case
    # A lone case has nothing to compare against yet.
    assert case["duplicate_score"] is None


def test_case_response_includes_is_possible_duplicate_field(client):
    case = _direct_case(client)
    assert "is_possible_duplicate" in case
    assert case["is_possible_duplicate"] is False


def test_list_cases_includes_duplicate_information(client):
    project, cases = _create_project_with_cases(client, count=3)

    listed = client.get(f"/projects/{project['id']}/cases").json()

    assert all("duplicate_score" in c and "is_possible_duplicate" in c for c in listed)


def test_missing_case_duplicate_fields_behave_as_404(client):
    response = client.get("/cases/999999")
    assert response.status_code == 404


# --- M7: grounding fields in API responses ------------------------------


def test_case_response_includes_grounding_score_field(client):
    case = _direct_case(client)
    assert "grounding_score" in case
    assert case["grounding_score"] is not None  # answerable, has evidence


def test_case_response_includes_needs_grounding_review_field(client):
    case = _direct_case(client)
    assert "needs_grounding_review" in case


def test_unanswerable_response_returns_null_grounding_score(client):
    case = _unanswerable_case(client)
    assert case["grounding_score"] is None
    assert case["needs_grounding_review"] is False


def test_list_cases_includes_grounding_information(client):
    project, cases = _create_project_with_cases(client, count=3)

    listed = client.get(f"/projects/{project['id']}/cases").json()

    assert all("grounding_score" in c and "needs_grounding_review" in c for c in listed)


def test_patch_response_contains_updated_grounding_data(client):
    case = _direct_case(client)

    updated = client.patch(
        f"/cases/{case['id']}", json={"reference_answer": "A different but valid answer."}
    ).json()

    assert "grounding_score" in updated
    assert "needs_grounding_review" in updated
