from tests.pdf_fixtures import build_minimal_pdf


def _create_project(client, name="Test Project"):
    return client.post("/projects", json={"name": name}).json()


def test_create_text_source(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/text",
        json={"title": "Employee Handbook", "text": "Employees receive 25 days of leave."},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "Employee Handbook"
    assert data["source_type"] == "text"
    assert data["raw_text"] == "Employees receive 25 days of leave."
    assert data["project_id"] == project["id"]


def test_create_text_source_defaults_filename(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/text",
        json={"text": "Some source text."},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "pasted-text"


def test_create_text_source_rejects_empty_text(client):
    project = _create_project(client)

    response = client.post(f"/projects/{project['id']}/sources/text", json={"text": ""})

    # Pydantic's min_length=1 rejects this before it reaches our own check.
    assert response.status_code == 422


def test_create_text_source_rejects_whitespace_only_text(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": "   \n\t  "}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Source text cannot be empty."


def test_create_text_source_for_nonexistent_project_returns_404(client):
    response = client.post("/projects/999999/sources/text", json={"text": "Some text."})

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_upload_txt(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("notes.txt", b"Employees receive 25 days of leave.", "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "notes.txt"
    assert data["source_type"] == "txt"
    assert data["raw_text"] == "Employees receive 25 days of leave."


def test_upload_markdown(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("handbook.md", b"# Handbook\n\nSome policy text.", "text/markdown")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "handbook.md"
    assert data["source_type"] == "markdown"
    assert "# Handbook" in data["raw_text"]


def test_upload_text_pdf(client):
    project = _create_project(client)
    pdf_bytes = build_minimal_pdf("Employees receive 25 days of annual leave per year.")

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("handbook.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["source_type"] == "pdf"
    assert "25 days" in data["raw_text"]


def test_upload_rejects_unsupported_file_type(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_pdf_with_no_extractable_text(client):
    project = _create_project(client)
    empty_pdf = build_minimal_pdf("")

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("scanned.pdf", empty_pdf, "application/pdf")},
    )

    assert response.status_code == 400
    assert "No extractable text was found" in response.json()["detail"]


def test_upload_rejects_file_over_size_limit(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)  # 0 bytes -- anything is "too big"
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("notes.txt", b"a", "text/plain")},
    )

    assert response.status_code == 400
    assert "exceeds" in response.json()["detail"]


def test_create_text_source_rejects_text_over_size_limit(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": "some text"}
    )

    assert response.status_code == 400
    assert "exceeds" in response.json()["detail"]


def test_list_project_sources(client):
    project = _create_project(client)
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "First", "text": "A"})
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Second", "text": "B"})

    response = client.get(f"/projects/{project['id']}/sources")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Newest first.
    assert [item["filename"] for item in data] == ["Second", "First"]
    assert "raw_text" not in data[0]
    assert data[0]["character_count"] == 1
    assert data[0]["preview"] == "B"


def test_get_single_source(client):
    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"title": "Doc", "text": "Full text here."}
    ).json()

    response = client.get(f"/sources/{created['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["raw_text"] == "Full text here."
    assert data["project_id"] == project["id"]


def test_get_nonexistent_source_returns_404(client):
    response = client.get("/sources/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found."


def test_delete_source(client):
    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": "Delete me."}
    ).json()

    delete_response = client.delete(f"/sources/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/sources/{created['id']}")
    assert get_response.status_code == 404


def test_delete_nonexistent_source_returns_404(client):
    response = client.delete("/sources/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found."


def test_source_belongs_to_correct_project(client):
    project_a = _create_project(client, "Project A")
    project_b = _create_project(client, "Project B")

    client.post(f"/projects/{project_a['id']}/sources/text", json={"title": "A doc", "text": "A"})
    client.post(f"/projects/{project_b['id']}/sources/text", json={"title": "B doc", "text": "B"})

    response = client.get(f"/projects/{project_a['id']}/sources")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "A doc"


def test_deleting_project_removes_its_sources(client):
    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": "Will be cascaded away."}
    ).json()

    delete_response = client.delete(f"/projects/{project['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/sources/{created['id']}")
    assert get_response.status_code == 404
