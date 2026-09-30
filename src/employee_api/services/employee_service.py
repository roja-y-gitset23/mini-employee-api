"""EmployeeService: CRUD, pagination and bulk import over StorageService."""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from employee_api.models.employee import Employee
from employee_api.schemas.common import ImportResult, ImportRowError
from employee_api.schemas.employee import (
    EmployeeCreate,
    EmployeePage,
    EmployeeResponse,
    EmployeeUpdate,
)
from employee_api.storage import StorageService
from employee_api.utils.decorators import log_execution
from employee_api.utils.logger import get_logger

logger = get_logger(__name__)

Record = Dict[str, Any]


class EmployeeNotFoundError(Exception):
    """Raised when an employee cannot be located."""


class DuplicateEmailError(Exception):
    """Raised when an email address is already used by another employee."""


class EmployeeService:
    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _email_exists(records: List[Record], email: str, exclude_id: Optional[int] = None) -> bool:
        target = email.strip().lower()
        return any(
            str(r.get("email", "")).lower() == target and r.get("id") != exclude_id
            for r in records
        )

    @staticmethod
    def _find_index(records: List[Record], employee_id: int) -> int:
        for index, record in enumerate(records):
            if record.get("id") == employee_id:
                return index
        raise EmployeeNotFoundError(f"Employee {employee_id} not found")

    def _new_record(self, records: List[Record], payload: Record) -> Record:
        next_id = max((int(r.get("id", 0)) for r in records), default=0) + 1
        now = self._now()
        return {"id": next_id, **payload, "created_at": now, "updated_at": now}

    @staticmethod
    def _format_validation_error(exc: ValidationError) -> str:
        return "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    @log_execution
    def list_employees(
        self, page: int = 1, page_size: int = 10, department: Optional[str] = None
    ) -> EmployeePage:
        records = self._storage.read_all()
        if department:
            wanted = department.strip().lower()
            records = [r for r in records if str(r.get("department", "")).lower() == wanted]

        total = len(records)
        pages = math.ceil(total / page_size) if total else 0
        start = (page - 1) * page_size
        items = [EmployeeResponse.model_validate(r) for r in records[start : start + page_size]]
        return EmployeePage(items=items, total=total, page=page, page_size=page_size, pages=pages)

    @log_execution
    def get_employee(self, employee_id: int) -> Employee:
        records = self._storage.read_all()
        index = self._find_index(records, employee_id)
        return Employee(**records[index])

    def find_by_email(self, email: str) -> Optional[Employee]:
        target = email.strip().lower()
        for record in self._storage.read_all():
            if str(record.get("email", "")).lower() == target:
                return Employee(**record)
        return None

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    @log_execution
    def create_employee(self, data: EmployeeCreate) -> Employee:
        with self._storage.transaction() as records:
            if self._email_exists(records, data.email):
                raise DuplicateEmailError(f"Email already in use: {data.email}")
            record = self._new_record(records, data.model_dump())
            records.append(record)
        logger.info("Created employee id=%s", record["id"])
        return Employee(**record)

    def _apply_changes(self, employee_id: int, changes: Record) -> Employee:
        with self._storage.transaction() as records:
            index = self._find_index(records, employee_id)
            new_email = changes.get("email")
            if new_email and self._email_exists(records, new_email, exclude_id=employee_id):
                raise DuplicateEmailError(f"Email already in use: {new_email}")
            records[index].update(changes)
            records[index]["updated_at"] = self._now()
            record = dict(records[index])
        return Employee(**record)

    @log_execution
    def replace_employee(self, employee_id: int, data: EmployeeCreate) -> Employee:
        employee = self._apply_changes(employee_id, data.model_dump())
        logger.info("Replaced employee id=%s", employee_id)
        return employee

    @log_execution
    def update_employee(self, employee_id: int, data: EmployeeUpdate) -> Employee:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        employee = self._apply_changes(employee_id, changes)
        logger.info("Updated employee id=%s fields=%s", employee_id, sorted(changes))
        return employee

    @log_execution
    def delete_employee(self, employee_id: int) -> None:
        with self._storage.transaction() as records:
            index = self._find_index(records, employee_id)
            records.pop(index)
        logger.info("Deleted employee id=%s", employee_id)

    @log_execution
    def bulk_create(self, rows: List[Record]) -> ImportResult:
        """Validate and insert many rows; invalid or duplicate rows are reported, not fatal."""
        imported = 0
        errors: List[ImportRowError] = []

        with self._storage.transaction() as records:
            for index, row in enumerate(rows, start=1):
                try:
                    data = EmployeeCreate.model_validate(row)
                except ValidationError as exc:
                    errors.append(
                        ImportRowError(row=index, error=self._format_validation_error(exc))
                    )
                    continue

                if self._email_exists(records, data.email):
                    errors.append(ImportRowError(row=index, error=f"Duplicate email: {data.email}"))
                    continue

                records.append(self._new_record(records, data.model_dump()))
                imported += 1

        logger.info("Bulk create: total=%s imported=%s skipped=%s", len(rows), imported, len(errors))
        return ImportResult(
            total=len(rows), imported=imported, skipped=len(errors), errors=errors
        )