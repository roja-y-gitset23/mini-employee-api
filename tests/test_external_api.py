import pytest
import requests

from employee_api.services.external_api_service import ExternalAPIClient, ExternalAPIError


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError("boom")

    def json(self):
        return self._payload


PAYLOAD = {
    "users": [
        {
            "firstName": "Ann",
            "lastName": "Lee",
            "email": "ann@example.com",
            "company": {"department": "Marketing", "title": "Designer"},
        },
        {"firstName": "NoEmail"},
        {"firstName": "Bare", "lastName": "Bones", "email": "bare@example.com", "company": None},
    ]
}


def test_session_retry_configuration():
    client = ExternalAPIClient("https://api.test/users")
    adapter = client.session.get_adapter("https://api.test/users")
    assert adapter.max_retries.total == 3
    assert 503 in adapter.max_retries.status_forcelist


def test_extract_employees_uses_nested_get_with_defaults():
    client = ExternalAPIClient("https://api.test/users", default_salary=1234.0)
    rows = client.extract_employees(PAYLOAD)
    assert len(rows) == 2
    assert rows[0] == {
        "name": "Ann Lee",
        "email": "ann@example.com",
        "department": "Marketing",
        "position": "Designer",
        "salary": 1234.0,
    }
    assert rows[1]["department"] == "Unassigned"
    assert rows[1]["position"] == "Employee"


def test_extract_employees_handles_unexpected_payload():
    client = ExternalAPIClient("https://api.test/users")
    assert client.extract_employees(None) == []
    assert client.extract_employees({}) == []


def test_fetch_employees_success(monkeypatch):
    client = ExternalAPIClient("https://api.test/users")
    monkeypatch.setattr(client.session, "get", lambda url, timeout=None: FakeResponse(PAYLOAD))
    assert len(client.fetch_employees()) == 2


def test_fetch_employees_http_error(monkeypatch):
    client = ExternalAPIClient("https://api.test/users")
    monkeypatch.setattr(client.session, "get", lambda url, timeout=None: FakeResponse({}, 500))
    with pytest.raises(ExternalAPIError):
        client.fetch_employees()


def test_fetch_employees_connection_error(monkeypatch):
    client = ExternalAPIClient("https://api.test/users")

    def _raise(url, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(client.session, "get", _raise)
    with pytest.raises(ExternalAPIError):
        client.fetch_employees()