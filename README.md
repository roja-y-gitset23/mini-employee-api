# Mini Employee Directory API

FastAPI service for managing an employee directory stored in `data/employees.json`.
Supports CRUD, pagination, CSV/Excel/PDF import, external API sync (with retries) and
HMAC SHA256 verified webhooks.

## Project layout

```
mini-employee-api/
├── src/employee_api/
│   ├── main.py            # app factory + exception handlers
│   ├── config.py          # env-based settings (python-dotenv)
│   ├── storage.py         # StorageService (atomic JSON persistence)
│   ├── api/               # routes.py, webhooks.py
│   ├── models/            # Employee domain model
│   ├── schemas/           # EmployeeCreate / EmployeeUpdate / EmployeeResponse
│   ├── services/          # EmployeeService, FileProcessor, ExternalAPIClient, WebhookService
│   └── utils/             # logger.py, decorators.py (@log_execution)
├── tests/
├── data/employees.json
└── ...
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env               # then edit WEBHOOK_SECRET
```

## Run

```bash
uvicorn employee_api.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

## Endpoints

| Method | Path                      | Description                                          |
|--------|---------------------------|------------------------------------------------------|
| GET    | `/employees`              | List employees (`page`, `page_size`, `department`)   |
| GET    | `/employees/{id}`         | Get one employee                                     |
| POST   | `/employees`              | Create employee                                      |
| PUT    | `/employees/{id}`         | Replace employee                                     |
| PATCH  | `/employees/{id}`         | Partial update                                       |
| DELETE | `/employees/{id}`         | Delete employee                                      |
| POST   | `/employees/import/csv`   | Import from CSV upload (`file`)                      |
| POST   | `/employees/import/excel` | Import from `.xlsx` upload (`file`)                  |
| POST   | `/employees/import/pdf`   | Import from text-based PDF upload (`file`)           |
| POST   | `/employees/sync`         | Background sync from the external API (202)          |
| POST   | `/webhooks/employee`      | Signed webhook receiver (202)                        |
| GET    | `/health`                 | Health check                                         |

### Validation rules

- `email`: valid format and unique (case-insensitive) -> `409` on duplicates
- `salary`: must be greater than 0
- `PATCH` requires at least one field

### Import formats

CSV / Excel: header row with `name, email, department, position, salary`.

PDF: one employee per line, pipe-delimited (tab or comma also accepted):

```
Name | Email | Department | Position | Salary
Erin Black | erin@example.com | Finance | Accountant | $72,000
```

Import responses report `total`, `imported`, `skipped` and per-row `errors`;
invalid or duplicate rows never abort the whole import.

### Webhooks

Send `POST /webhooks/employee` with header `X-Signature-256: sha256=<hex>` where the value is
the HMAC SHA256 of the raw request body keyed with `WEBHOOK_SECRET`.

Supported events: `employee.created`, `employee.updated`, `employee.deleted`.

```json
{
  "event": "employee.updated",
  "data": { "employee": { "email": "alice@example.com", "position": "Lead" } }
}
```

Example:

```bash
BODY='{"event":"employee.created","data":{"employee":{"name":"Jane Roe","email":"jane@example.com","department":"HR","position":"Recruiter","salary":60000}}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')

curl -X POST http://127.0.0.1:8000/webhooks/employee \
  -H "Content-Type: application/json" \
  -H "X-Signature-256: sha256=$SIG" \
  -d "$BODY"
```

Events are processed in a `BackgroundTask`; invalid signatures return `401`.

### External sync

`POST /employees/sync` schedules a background job that calls `EXTERNAL_API_URL` through a
`requests.Session` mounted with `HTTPAdapter(max_retries=Retry(total=3, ...))`, extracts nested
JSON via safe `.get()` lookups and bulk-imports the result (duplicates skipped).

## Tests

```bash
pytest
```

## Lint / hooks

```bash
pre-commit install
pre-commit run --all-files
```

## Logging

Centralised in `utils/logger.py` (console + rotating file at `LOG_FILE`). Service methods are
instrumented with `@log_execution` (start/end/duration/failure; arguments are never logged).