from tests.pdf_fixtures import build_minimal_pdf


def _create_project(client, name="Test Project"):
    return client.post("/projects", json={"name": name}).json()


def _long_text(paragraphs=5, words_per_paragraph=400):
    """A multi-paragraph document big enough to require several chunks
    with the default 750-word target."""
    return "\n\n".join(
        " ".join(f"p{p}_word{w}" for w in range(words_per_paragraph)) for p in range(paragraphs)
    )


def test_pasted_source_automatically_creates_chunks(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/text",
        json={"title": "Doc", "text": "Employees receive 25 days of leave."},
    )

    assert response.status_code == 201
    assert response.json()["chunk_count"] == 1


def test_txt_source_automatically_creates_chunks(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("notes.txt", _long_text().encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["chunk_count"] > 1


def test_markdown_source_automatically_creates_chunks(client):
    project = _create_project(client)

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("handbook.md", _long_text().encode("utf-8"), "text/markdown")},
    )

    assert response.status_code == 201
    assert response.json()["chunk_count"] > 1


def test_pdf_source_automatically_creates_chunks(client):
    project = _create_project(client)
    pdf_bytes = build_minimal_pdf("Employees receive 25 days of annual leave per year.")

    response = client.post(
        f"/projects/{project['id']}/sources/upload",
        files={"file": ("handbook.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["chunk_count"] == 1


def test_chunk_indexes_are_ordered(client):
    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": _long_text()}
    ).json()

    response = client.get(f"/sources/{created['id']}/chunks")

    assert response.status_code == 200
    chunks = response.json()
    assert len(chunks) > 1
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_get_source_chunks_returns_correct_chunks(client):
    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text",
        json={"text": "Employees receive 25 days of annual leave per year."},
    ).json()

    response = client.get(f"/sources/{created['id']}/chunks")

    assert response.status_code == 200
    chunks = response.json()
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["source_document_id"] == created["id"]
    assert chunk["chunk_index"] == 0
    assert chunk["text"] == "Employees receive 25 days of annual leave per year."
    assert chunk["word_count"] == 9


def test_get_chunks_for_nonexistent_source_returns_404(client):
    response = client.get("/sources/999999/chunks")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found."


def test_deleting_source_removes_its_chunks(client, db_session):
    from app.models.chunk import SourceChunk

    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": _long_text()}
    ).json()

    chunks_before = client.get(f"/sources/{created['id']}/chunks").json()
    assert len(chunks_before) > 1

    delete_response = client.delete(f"/sources/{created['id']}")
    assert delete_response.status_code == 204

    remaining = db_session.query(SourceChunk).filter_by(source_document_id=created["id"]).all()
    assert remaining == []


def test_deleting_project_removes_chunks(client, db_session):
    from app.models.chunk import SourceChunk

    project = _create_project(client)
    created = client.post(
        f"/projects/{project['id']}/sources/text", json={"text": _long_text()}
    ).json()

    chunk_ids = [c["id"] for c in client.get(f"/sources/{created['id']}/chunks").json()]
    assert len(chunk_ids) > 1

    delete_response = client.delete(f"/projects/{project['id']}")
    assert delete_response.status_code == 204

    remaining = db_session.query(SourceChunk).filter(SourceChunk.id.in_(chunk_ids)).all()
    assert remaining == []


def test_chunks_belong_to_correct_source(client):
    project = _create_project(client)
    source_a = client.post(
        f"/projects/{project['id']}/sources/text", json={"title": "A", "text": "Source A text."}
    ).json()
    source_b = client.post(
        f"/projects/{project['id']}/sources/text", json={"title": "B", "text": "Source B text."}
    ).json()

    chunks_a = client.get(f"/sources/{source_a['id']}/chunks").json()
    chunks_b = client.get(f"/sources/{source_b['id']}/chunks").json()

    assert all(c["source_document_id"] == source_a["id"] for c in chunks_a)
    assert all(c["source_document_id"] == source_b["id"] for c in chunks_b)
    assert chunks_a[0]["text"] == "Source A text."
    assert chunks_b[0]["text"] == "Source B text."


def test_source_summary_reports_correct_chunk_count(client):
    project = _create_project(client)
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Short", "text": "One chunk."})
    client.post(f"/projects/{project['id']}/sources/text", json={"title": "Long", "text": _long_text()})

    response = client.get(f"/projects/{project['id']}/sources")

    assert response.status_code == 200
    by_name = {item["filename"]: item for item in response.json()}
    assert by_name["Short"]["chunk_count"] == 1
    assert by_name["Long"]["chunk_count"] > 1


def test_existing_unchunked_source_is_chunked_on_demand(client, db_session):
    """Simulates an M2-era source that was created before chunking existed:
    a SourceDocument row with no SourceChunk rows. GET .../chunks should
    lazily backfill chunks for it (see the M3 "Existing Sources" decision).
    """
    from app.models.chunk import SourceChunk
    from app.models.source import SourceDocument, SourceType

    project = _create_project(client)
    source = SourceDocument(
        project_id=project["id"],
        filename="pre-m3.txt",
        source_type=SourceType.TXT,
        raw_text="Pre-existing source with no chunks yet.",
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    assert (
        db_session.query(SourceChunk).filter_by(source_document_id=source.id).count() == 0
    )

    response = client.get(f"/sources/{source.id}/chunks")

    assert response.status_code == 200
    chunks = response.json()
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Pre-existing source with no chunks yet."
