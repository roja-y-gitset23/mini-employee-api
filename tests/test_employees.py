from employee_api.services.employee_service import EmployeeService
from employee_api.storage import StorageService


def _create(client, payload, **overrides):
    return client.post("/employees", json={**payload, **overrides})


def test_create_and_get(client, payload):
    created = _create(client, payload)
    assert created.status_code == 201
    body = created.json()
    assert body["id"] == 1
    assert body["email"] == "alice@example.com"

    fetched = client.get(f"/employees/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Alice Smith"


def test_get_not_found(client):
    assert client.get("/employees/999").status_code == 404


def test_duplicate_email_rejected_case_insensitive(client, payload):
    assert _create(client, payload).status_code == 201
    response = _create(client, payload, email="ALICE@example.com")
    assert response.status_code == 409


def test_invalid_email_rejected(client, payload):
    assert _create(client, payload, email="not-an-email").status_code == 422


def test_non_positive_salary_rejected(client, payload):
    assert _create(client, payload, salary=0).status_code == 422
    assert _create(client, payload, salary=-10).status_code == 422


def test_pagination(client, payload):
    for i in range(5):
        assert _create(client, payload, email=f"user{i}@example.com").status_code == 201

    page = client.get("/employees", params={"page": 3, "page_size": 2}).json()
    assert page["total"] == 5
    assert page["pages"] == 3
    assert page["page"] == 3
    assert len(page["items"]) == 1

    first = client.get("/employees", params={"page": 1, "page_size": 2}).json()
    assert [e["id"] for e in first["items"]] == [1, 2]


def test_pagination_validation(client):
    assert client.get("/employees", params={"page": 0}).status_code == 422
    assert client.get("/employees", params={"page_size": 1000}).status_code == 422


def test_department_filter(client, payload):
    _create(client, payload)
    _create(client, payload, email="bob@example.com", department="Sales")
    result = client.get("/employees", params={"department": "sales"}).json()
    assert result["total"] == 1
    assert result["items"][0]["email"] == "bob@example.com"


def test_put_replaces(client, payload):
    employee_id = _create(client, payload).json()["id"]
    new_payload = {**payload, "name": "Alice Jones", "salary": 90000}
    response = client.put(f"/employees/{employee_id}", json=new_payload)
    assert response.status_code == 200
    assert response.json()["name"] == "Alice Jones"
    assert response.json()["salary"] == 90000


def test_put_duplicate_email_conflict(client, payload):
    _create(client, payload)
    other_id = _create(client, payload, email="bob@example.com").json()["id"]
    response = client.put(f"/employees/{other_id}", json=payload)
    assert response.status_code == 409


def test_patch_partial_update(client, payload):
    employee_id = _create(client, payload).json()["id"]
    response = client.patch(f"/employees/{employee_id}", json={"position": "Lead"})
    assert response.status_code == 200
    body = response.json()
    assert body["position"] == "Lead"
    assert body["name"] == "Alice Smith"


def test_patch_empty_body_rejected(client, payload):
    employee_id = _create(client, payload).json()["id"]
    assert client.patch(f"/employees/{employee_id}", json={}).status_code == 422


def test_patch_not_found(client):
    assert client.patch("/employees/42", json={"position": "X"}).status_code == 404


def test_delete(client, payload):
    employee_id = _create(client, payload).json()["id"]
    assert client.delete(f"/employees/{employee_id}").status_code == 204
    assert client.get(f"/employees/{employee_id}").status_code == 404
    assert client.delete(f"/employees/{employee_id}").status_code == 404


def test_data_persisted_to_json_file(tmp_path, payload):
    path = tmp_path / "data" / "employees.json"
    service = EmployeeService(StorageService(path))
    from employee_api.schemas.employee import EmployeeCreate

    service.create_employee(EmployeeCreate(**payload))
    reloaded = EmployeeService(StorageService(path))
    assert reloaded.get_employee(1).email == "alice@example.com"
    assert path.exists()