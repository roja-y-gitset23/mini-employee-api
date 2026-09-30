"""ExternalAPIClient (retrying HTTP client) and WebhookService (HMAC verified events)."""

import hashlib
import hmac
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from employee_api.schemas.employee import EmployeeCreate, EmployeeUpdate
from employee_api.services.employee_service import EmployeeService
from employee_api.utils.decorators import log_execution
from employee_api.utils.logger import get_logger

logger = get_logger(__name__)


class ExternalAPIError(RuntimeError):
    """Raised when the external API cannot be reached or returns invalid data."""


class ExternalAPIClient:
    """Fetches employees from an external API using a session with retry logic."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        default_salary: float = 50000.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.default_salary = default_salary
        self.session = session or self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {"Accept": "application/json", "User-Agent": "mini-employee-api/1.0"}
        )
        return session

    @log_execution
    def fetch_employees(self) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExternalAPIError(f"Failed to fetch employees: {exc}") from exc
        return self.extract_employees(payload)

    def extract_employees(self, payload: Any) -> List[Dict[str, Any]]:
        """Map nested external JSON to employee rows using safe .get() lookups.

        Expected shape (DummyJSON style)::

            {"users": [{"firstName": "..", "lastName": "..", "email": "..",
                        "company": {"department": "..", "title": ".."}}]}
        """
        if isinstance(payload, dict):
            items = payload.get("users") or payload.get("data") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        rows: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            company = item.get("company") or {}
            name = " ".join(
                part for part in (item.get("firstName"), item.get("lastName")) if part
            ) or item.get("name")
            email = item.get("email")
            if not name or not email:
                logger.warning("Skipping external record without name/email")
                continue
            rows.append(
                {
                    "name": name,
                    "email": email,
                    "department": company.get("department") or "Unassigned",
                    "position": company.get("title") or "Employee",
                    "salary": item.get("salary") or self.default_salary,
                }
            )
        return rows


class WebhookService:
    """Verifies HMAC SHA256 signatures and applies employee events."""

    _FIELDS = ("name", "email", "department", "position", "salary")

    def __init__(self, secret: str, employee_service: EmployeeService) -> None:
        self._secret = secret or ""
        self._employees = employee_service

    @property
    def secret_configured(self) -> bool:
        return bool(self._secret)

    def compute_signature(self, body: bytes) -> str:
        return hmac.new(self._secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def verify_signature(self, body: bytes, signature: Optional[str]) -> bool:
        if not signature or not self._secret:
            return False
        provided = signature.strip()
        if provided.lower().startswith("sha256="):
            provided = provided[len("sha256="):]
        return hmac.compare_digest(self.compute_signature(body), provided.lower())

    @log_execution
    def process_event(self, payload: Dict[str, Any]) -> None:
        """Handle an event payload. Runs in the background so errors are logged, not raised."""
        event = payload.get("event")
        employee = (payload.get("data") or {}).get("employee") or {}
        try:
            if event == "employee.created":
                self._handle_created(employee)
            elif event == "employee.updated":
                self._handle_updated(employee)
            elif event == "employee.deleted":
                self._handle_deleted(employee)
            else:
                logger.warning("Ignoring unsupported webhook event: %s", event)
        except Exception:
            logger.exception("Failed to process webhook event '%s'", event)

    def _handle_created(self, employee: Dict[str, Any]) -> None:
        data = EmployeeCreate(**{f: employee.get(f) for f in self._FIELDS})
        self._employees.create_employee(data)

    def _resolve_id(self, employee: Dict[str, Any]) -> int:
        employee_id = employee.get("id")
        if employee_id is not None:
            return int(employee_id)
        email = employee.get("email")
        if email:
            found = self._employees.find_by_email(email)
            if found:
                return found.id
        raise ValueError("Webhook employee must reference an existing 'id' or 'email'")

    def _handle_updated(self, employee: Dict[str, Any]) -> None:
        employee_id = self._resolve_id(employee)
        changes = {f: employee.get(f) for f in self._FIELDS if employee.get(f) is not None}
        self._employees.update_employee(employee_id, EmployeeUpdate(**changes))

    def _handle_deleted(self, employee: Dict[str, Any]) -> None:
        self._employees.delete_employee(self._resolve_id(employee))