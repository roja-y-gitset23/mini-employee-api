from io import BytesIO

import fitz
from openpyxl import Workbook

HEADER = ["Name", "Email", "Department", "Position", "Salary"]


def _csv_bytes() -> bytes:
    lines = [
        ",".join(HEADER),
        "Alice Smith,alice@example.com,Engineering,Developer,85000",
        "Bob Brown,bob@example.com,Sales,Manager,70000",
        "Bad Email,not-an-email,Sales,Rep,1000",
        "Neg Salary,neg@example.com,Sales,Rep,-5",
        "Dup Alice,alice@example.com,Sales,Rep,1000",
    ]
    return "\n".join(lines).encode("utf-8")


def _excel_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append(["Carol White", "carol@example.com", "HR", "Recruiter", 60000])
    sheet.append(["Dan Green", "dan@example.com", "HR", "Analyst", 62000.5])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pdf_bytes(lines) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 72), "\n".join(lines), fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def test_import_csv(client):
    response = client.post(
        "/employees/import/csv", files={"file": ("emps.csv", _csv_bytes(), "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["imported"] == 2
    assert body["skipped"] == 3
    assert {e["row"] for e in body["errors"]} == {3, 4, 5}
    assert client.get("/employees").json()["total"] == 2


def test_import_csv_missing_columns(client):
    response = client.post(
        "/employees/import/csv", files={"file": ("emps.csv", b"name,email\nA,a@example.com", "text/csv")}
    )
    assert response.status_code == 422


def test_import_rejects_wrong_extension(client):
    response = client.post(
        "/employees/import/csv", files={"file": ("emps.txt", b"data", "text/plain")}
    )
    assert response.status_code == 400


def test_import_rejects_empty_file(client):
    response = client.post(
        "/employees/import/csv", files={"file": ("emps.csv", b"", "text/csv")}
    )
    assert response.status_code == 400


def test_import_excel(client):
    response = client.post(
        "/employees/import/excel",
        files={
            "file": (
                "emps.xlsx",
                _excel_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 2
    assert client.get("/employees").json()["total"] == 2


def test_import_excel_invalid_file(client):
    response = client.post(
        "/employees/import/excel", files={"file": ("emps.xlsx", b"not excel", "application/octet-stream")}
    )
    assert response.status_code == 422


def test_import_pdf(client):
    pdf = _pdf_bytes(
        [
            "Employee Report",
            "Name | Email | Department | Position | Salary",
            "Erin Black | erin@example.com | Finance | Accountant | $72,000",
            "Frank Gray | frank@example.com | Finance | Controller | 95000",
        ]
    )
    response = client.post(
        "/employees/import/pdf", files={"file": ("emps.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    listing = client.get("/employees").json()["items"]
    assert {e["email"] for e in listing} == {"erin@example.com", "frank@example.com"}
    assert 72000 in {e["salary"] for e in listing}


def test_import_pdf_without_records(client):
    pdf = _pdf_bytes(["Just some text", "Nothing useful here"])
    response = client.post(
        "/employees/import/pdf", files={"file": ("emps.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 422


def test_import_pdf_invalid_file(client):
    response = client.post(
        "/employees/import/pdf", files={"file": ("emps.pdf", b"garbage", "application/pdf")}
    )
    assert response.status_code == 422


def test_sync_imports_from_external_api(client, fake_external):
    fake_external.employees = [
        {
            "name": "Gina Hall",
            "email": "gina@example.com",
            "department": "Ops",
            "position": "Coordinator",
            "salary": 50000,
        }
    ]
    response = client.post("/employees/sync")
    assert response.status_code == 202
    listing = client.get("/employees").json()
    assert listing["total"] == 1
    assert listing["items"][0]["email"] == "gina@example.com"