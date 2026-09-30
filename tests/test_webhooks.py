import hashlib
import hmac
import json

from tests.conftest import WEBHOOK_SECRET


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(client, payload, signature=None, sign=True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Signature-256"] = signature
    elif sign:
        headers["X-Signature-256"] = _sign(body)
    return client.post("/webhooks/employee", content=body, headers=headers)


def _event(event, employee):
    return {"event": event, "data": {"employee": employee}}


def test_created_event(client, payload):
    response = _post(client, _event("employee.created", payload))
    assert response.status_code == 202
    listing = client.get("/employees").json()
    assert listing["total"] == 1
    assert listing["items"][0]["email"] == "alice@example.com"


def test_updated_event_by_email(client, payload):
    client.post("/employees", json=payload)
    response = _post(
        client,
        _event("employee.updated", {"email": "alice@example.com", "position": "Principal"}),
    )
    assert response.status_code == 202
    assert client.get("/employees/1").json()["position"] == "Principal"


def test_deleted_event_by_id(client, payload):
    client.post("/employees", json=payload)
    response = _post(client, _event("employee.deleted", {"id": 1}))
    assert response.status_code == 202
    assert client.get("/employees/1").status_code == 404


def test_invalid_signature_rejected(client, payload):
    body_payload = _event("employee.created", payload)
    response = _post(client, body_payload, signature="sha256=" + "0" * 64)
    assert response.status_code == 401
    assert client.get("/employees").json()["total"] == 0


def test_signature_from_wrong_secret_rejected(client, payload):
    body = json.dumps(_event("employee.created", payload)).encode()
    response = client.post(
        "/webhooks/employee",
        content=body,
        headers={"X-Signature-256": _sign(body, "other-secret")},
    )
    assert response.status_code == 401


def test_missing_signature_rejected(client, payload):
    response = _post(client, _event("employee.created", payload), sign=False)
    assert response.status_code == 401


def test_invalid_json_rejected(client):
    body = b"{not json"
    response = client.post(
        "/webhooks/employee", content=body, headers={"X-Signature-256": _sign(body)}
    )
    assert response.status_code == 400


def test_missing_event_rejected(client):
    assert _post(client, {"data": {}}).status_code == 400


def test_unknown_event_is_accepted_but_ignored(client):
    response = _post(client, _event("employee.unknown", {}))
    assert response.status_code == 202
    assert client.get("/employees").json()["total"] == 0


def test_invalid_employee_data_does_not_crash(client):
    response = _post(client, _event("employee.created", {"name": "X", "email": "bad"}))
    assert response.status_code == 202
    assert client.get("/employees").json()["total"] == 0