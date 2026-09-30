import pytest
from fastapi.testclient import TestClient

from employee_api.api import routes
from employee_api.api.webhooks import get_webhook_service
from employee_api.main import app
from employee_api.services.employee_service import EmployeeService
from employee_api.services.external_api_service import WebhookService
from employee_api.storage import StorageService

WEBHOOK_SECRET = "test-secret"


class FakeExternalClient:
    def __init__(self, employees=None):
        self.employees = employees or []

    def fetch_employees(self):
        return self.employees


@pytest.fixture
def employee_service(tmp_path):
    return EmployeeService(StorageService(tmp_path / "employees.json"))


@pytest.fixture
def fake_external():
    return FakeExternalClient()


@pytest.fixture
def client(employee_service, fake_external):
    app.dependency_overrides[routes.get_employee_service] = lambda: employee_service
    app.dependency_overrides[routes.get_external_client] = lambda: fake_external
    app.dependency_overrides[get_webhook_service] = lambda: WebhookService(
        WEBHOOK_SECRET, employee_service
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def payload():
    return {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "department": "Engineering",
        "position": "Developer",
        "salary": 85000,
    }