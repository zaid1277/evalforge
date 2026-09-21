import csv
import io
import json

import pytest

from app.config import settings
from app.services import export_service


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test in this file runs against MockProvider -- no test here
    ever calls a real LLM."""
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


def _create_project_with_cases(client, count=5, test_types=None, text=None, name="Export Test Project"):
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
    cases = response.json()["cases"]
    return project, cases


def _approve(client, case):
    return client.patch(f"/cases/{case['id']}", json={"status": "approved"}).json()


def _reject(client, case):
    return client.patch(f"/cases/{case['id']}", json={"status": "rejected"}).json()


def _project_with_approved_cases(client, count=3):
    project, cases = _create_project_with_cases(client, count=count, test_types=["direct"])
    approved = [_approve(client, c) for c in cases]
    return project, approved


def _parse_jsonl(text):
    lines = [line for line in text.split("\n") if line.strip()]
    return [json.loads(line) for line in lines]


def _parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


# --- JSONL correctness ---------------------------------------------------


def test_jsonl_is_default_format(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")


def test_jsonl_one_object_per_line(client):
    project, cases = _project_with_approved_cases(client, count=3)

    response = client.get(f"/projects/{project['id']}/export?format=jsonl")

    rows = _parse_jsonl(response.text)
    assert len(rows) == 3


def test_jsonl_not_a_single_json_array(client):
    project, cases = _project_with_approved_cases(client, count=2)

    response = client.get(f"/projects/{project['id']}/export?format=jsonl")

    # A JSON array would parse whole-text as one value starting with '['.
    assert not response.text.strip().startswith("[")


def test_jsonl_rows_contain_all_expected_fields(client):
    project, cases = _project_with_approved_cases(client, count=1)

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    assert set(export_service.EXPORT_FIELDS) == set(rows[0].keys())


def test_jsonl_excludes_computed_flags(client):
    project, cases = _project_with_approved_cases(client, count=1)

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    assert "is_possible_duplicate" not in rows[0]
    assert "needs_grounding_review" not in rows[0]


def test_jsonl_unanswerable_case_has_null_reference_answer(client):
    project, cases = _create_project_with_cases(client, count=1, test_types=["unanswerable"])
    approved = _approve(client, cases[0])

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    assert rows[0]["reference_answer"] is None
    assert rows[0]["id"] == approved["id"]


def test_jsonl_preserves_unicode_without_escaping(client):
    project, cases = _create_project_with_cases(
        client,
        count=1,
        test_types=["direct"],
        text="L'entreprise offre 25 jours de congé annuel. Le café est gratuit à l'accueil.",
    )
    _approve(client, cases[0])

    response = client.get(f"/projects/{project['id']}/export")

    # ensure_ascii=False: real accented characters appear raw, not as \u escapes.
    assert "\\u00e9" not in response.text
    assert "\\u00e0" not in response.text


def test_jsonl_source_chunk_ids_is_a_list(client):
    project, cases = _project_with_approved_cases(client, count=1)

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    assert isinstance(rows[0]["source_chunk_ids"], list)
    assert all(isinstance(cid, int) for cid in rows[0]["source_chunk_ids"])


def test_jsonl_scores_match_case_detail_endpoint(client):
    project, cases = _project_with_approved_cases(client, count=2)
    detail = client.get(f"/cases/{cases[0]['id']}").json()

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)
    row = next(r for r in rows if r["id"] == cases[0]["id"])

    assert row["duplicate_score"] == detail["duplicate_score"]
    assert row["grounding_score"] == detail["grounding_score"]


def test_jsonl_source_chunk_ids_match_evidence_endpoint(client):
    project, cases = _project_with_approved_cases(client, count=1)
    evidence = client.get(f"/cases/{cases[0]['id']}/sources").json()

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)
    row = next(r for r in rows if r["id"] == cases[0]["id"])

    assert row["source_chunk_ids"] == [c["id"] for c in evidence]


# --- CSV correctness -------------------------------------------------------


def test_csv_content_type(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_csv_header_matches_export_fields(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export?format=csv")
    header = response.text.splitlines()[0].split(",")

    assert header == export_service.EXPORT_FIELDS


def test_csv_row_count_matches_case_count(client):
    project, cases = _project_with_approved_cases(client, count=3)

    rows = _parse_csv(client.get(f"/projects/{project['id']}/export?format=csv").text)

    assert len(rows) == 3


def test_csv_unanswerable_case_has_blank_reference_answer(client):
    project, cases = _create_project_with_cases(client, count=1, test_types=["unanswerable"])
    _approve(client, cases[0])

    rows = _parse_csv(client.get(f"/projects/{project['id']}/export?format=csv").text)

    assert rows[0]["reference_answer"] == ""


def test_csv_source_chunk_ids_are_pipe_separated(client):
    long_text = "\n\n".join(f"Paragraph {i}. " + ("word " * 800) for i in range(3))
    project, cases = _create_project_with_cases(client, count=1, test_types=["multi_step"], text=long_text)
    _approve(client, cases[0])

    rows = _parse_csv(client.get(f"/projects/{project['id']}/export?format=csv").text)

    assert "," not in rows[0]["source_chunk_ids"]
    if rows[0]["source_chunk_ids"]:
        parts = rows[0]["source_chunk_ids"].split("|")
        assert all(part.isdigit() for part in parts)


def test_csv_handles_embedded_commas_and_quotes(client):
    project, cases = _create_project_with_cases(
        client,
        count=1,
        test_types=["direct"],
        text='The policy states: "employees, contractors, and interns" all qualify for leave.',
    )
    case = cases[0]
    client.patch(
        f"/cases/{case['id']}",
        json={"question": 'Does this cover "employees, contractors, and interns"?'},
    )
    _approve(client, case)

    response = client.get(f"/projects/{project['id']}/export?format=csv")
    rows = _parse_csv(response.text)

    assert rows[0]["question"] == 'Does this cover "employees, contractors, and interns"?'


# --- Filtering / status ----------------------------------------------------


def test_default_export_is_approved_only(client):
    project, cases = _create_project_with_cases(client, count=3, test_types=["direct"])
    approved = _approve(client, cases[0])
    _reject(client, cases[1])
    # cases[2] stays "generated"

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    assert len(rows) == 1
    assert rows[0]["id"] == approved["id"]
    assert rows[0]["status"] == "approved"


def test_rejected_and_generated_never_leak_into_approved_export(client):
    project, cases = _create_project_with_cases(client, count=3, test_types=["direct"])
    _approve(client, cases[0])
    _reject(client, cases[1])
    # cases[2] stays "generated"

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export?status=approved").text)

    statuses = {r["status"] for r in rows}
    assert statuses == {"approved"}


def test_status_generated_returns_only_generated(client):
    project, cases = _create_project_with_cases(client, count=2, test_types=["direct"])
    _approve(client, cases[0])
    # cases[1] stays "generated"

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export?status=generated").text)

    assert len(rows) == 1
    assert rows[0]["status"] == "generated"


def test_status_rejected_returns_only_rejected(client):
    project, cases = _create_project_with_cases(client, count=2, test_types=["direct"])
    _reject(client, cases[0])
    # cases[1] stays "generated"

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export?status=rejected").text)

    assert len(rows) == 1
    assert rows[0]["status"] == "rejected"


def test_status_all_includes_every_status(client):
    project, cases = _create_project_with_cases(client, count=3, test_types=["direct"])
    _approve(client, cases[0])
    _reject(client, cases[1])
    # cases[2] stays "generated"

    rows = _parse_jsonl(client.get(f"/projects/{project['id']}/export?status=all").text)

    assert {r["status"] for r in rows} == {"approved", "rejected", "generated"}
    assert len(rows) == 3


def test_export_excludes_cases_from_other_projects(client):
    project_a, cases_a = _project_with_approved_cases(client, count=1)
    project_b, cases_b = _project_with_approved_cases(client, count=1)

    rows = _parse_jsonl(client.get(f"/projects/{project_a['id']}/export").text)

    assert len(rows) == 1
    assert rows[0]["id"] == cases_a[0]["id"]
    assert rows[0]["id"] != cases_b[0]["id"]


def test_deterministic_ordering_is_stable_across_repeated_calls(client):
    project, cases = _project_with_approved_cases(client, count=5)

    first = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)
    second = _parse_jsonl(client.get(f"/projects/{project['id']}/export").text)

    ids_first = [r["id"] for r in first]
    ids_second = [r["id"] for r in second]
    assert ids_first == ids_second
    assert ids_first == sorted(ids_first)


# --- HTTP / errors -----------------------------------------------------


def test_export_missing_project_returns_404(client):
    response = client.get("/projects/999999/export")

    assert response.status_code == 404


def test_export_missing_project_does_not_return_a_file(client):
    response = client.get("/projects/999999/export")

    assert "content-disposition" not in response.headers


def test_export_empty_approved_dataset_returns_400(client):
    project = client.post("/projects", json={"name": "Empty Project"}).json()

    response = client.get(f"/projects/{project['id']}/export")

    assert response.status_code == 400
    assert "approved" in response.json()["detail"].lower()


def test_export_empty_generated_dataset_message_mentions_generated(client):
    project, cases = _project_with_approved_cases(client, count=1)  # all approved, none generated

    response = client.get(f"/projects/{project['id']}/export?status=generated")

    assert response.status_code == 400
    assert "generated" in response.json()["detail"].lower()


def test_export_invalid_format_returns_422(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export?format=xml")

    assert response.status_code == 422


def test_export_invalid_status_returns_422(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export?status=pending")

    assert response.status_code == 422


# --- Filename / Content-Disposition safety -------------------------------


def test_filename_is_sanitized_for_unsafe_project_name(client):
    project, cases = _create_project_with_cases(
        client, count=1, test_types=["direct"], name="Employee Handbook / 2026!"
    )
    _approve(client, cases[0])

    response = client.get(f"/projects/{project['id']}/export")

    disposition = response.headers["content-disposition"]
    assert "/" not in disposition.split("filename=")[1]
    assert "\r" not in disposition and "\n" not in disposition
    assert "employee-handbook-2026-approved.jsonl" in disposition


def test_filename_falls_back_for_names_with_no_safe_characters(client):
    project, cases = _create_project_with_cases(client, count=1, test_types=["direct"], name="日本語プロジェクト")
    _approve(client, cases[0])

    response = client.get(f"/projects/{project['id']}/export")

    assert "evalforge-dataset-approved.jsonl" in response.headers["content-disposition"]


def test_content_disposition_is_attachment(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export")

    assert response.headers["content-disposition"].startswith("attachment")


def test_csv_filename_has_csv_extension(client):
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(f"/projects/{project['id']}/export?format=csv")

    assert response.headers["content-disposition"].endswith('.csv"')


def test_content_disposition_is_exposed_via_cors(client):
    """A cross-origin fetch() in the browser can only read
    response.headers.get('content-disposition') if the server explicitly
    exposes it via CORS -- it isn't on the default safelist. Without this,
    the frontend's filename extraction silently falls back to a generic
    name (caught during M8 manual verification)."""
    project, cases = _project_with_approved_cases(client, count=1)

    response = client.get(
        f"/projects/{project['id']}/export", headers={"Origin": "http://localhost:3000"}
    )

    assert "content-disposition" in response.headers.get("access-control-expose-headers", "").lower()


# --- No recalculation / no side effects -----------------------------------


def test_export_does_not_call_embedding_service(client, monkeypatch):
    project, cases = _project_with_approved_cases(client, count=2)

    calls = []
    import app.services.embedding_service as embedding_service

    monkeypatch.setattr(
        embedding_service, "embed_texts", lambda texts: calls.append(texts) or (_ for _ in ()).throw(AssertionError())
    )

    response = client.get(f"/projects/{project['id']}/export")

    assert response.status_code == 200
    assert calls == []


def test_export_does_not_change_stored_scores(client):
    project, cases = _project_with_approved_cases(client, count=2)
    before = client.get(f"/cases/{cases[0]['id']}").json()

    client.get(f"/projects/{project['id']}/export")

    after = client.get(f"/cases/{cases[0]['id']}").json()
    assert after["duplicate_score"] == before["duplicate_score"]
    assert after["grounding_score"] == before["grounding_score"]
