def test_create_project(client):
    response = client.post(
        "/projects",
        json={"name": "Employee Handbook Evaluation", "description": "A test project."},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Employee Handbook Evaluation"
    assert data["description"] == "A test project."
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_create_project_without_description(client):
    response = client.post("/projects", json={"name": "Minimal Project"})

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Minimal Project"
    assert data["description"] is None


def test_create_project_rejects_missing_name(client):
    response = client.post("/projects", json={"description": "No name provided."})

    assert response.status_code == 422


def test_create_project_rejects_empty_name(client):
    response = client.post("/projects", json={"name": ""})

    assert response.status_code == 422


def test_list_projects_empty(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_returns_newest_first(client):
    client.post("/projects", json={"name": "First"})
    client.post("/projects", json={"name": "Second"})

    response = client.get("/projects")

    assert response.status_code == 200
    names = [project["name"] for project in response.json()]
    assert names == ["Second", "First"]


def test_get_existing_project(client):
    created = client.post("/projects", json={"name": "Lookup Me"}).json()

    response = client.get(f"/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Lookup Me"


def test_get_nonexistent_project_returns_404(client):
    response = client.get("/projects/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_delete_project(client):
    created = client.post("/projects", json={"name": "Delete Me"}).json()

    delete_response = client.delete(f"/projects/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/projects/{created['id']}")
    assert get_response.status_code == 404


def test_delete_nonexistent_project_returns_404(client):
    response = client.delete("/projects/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."
