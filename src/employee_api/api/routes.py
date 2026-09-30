"""Employee, import, sync and health routes."""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool

from employee_api.config import get_settings
from employee_api.schemas.common import HealthResponse, ImportResult, MessageResponse
from employee_api.schemas.employee import (
    EmployeeCreate,
    EmployeePage,
    EmployeeResponse,
    EmployeeUpdate,
)
from employee_api.services.employee_service import EmployeeService
from employee_api.services.external_api_service import ExternalAPIClient, ExternalAPIError
from employee_api.services.file_service import FileProcessingError, FileProcessor
from employee_api.storage import StorageService
from employee_api.utils.decorators import log_execution
from employee_api.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Dependency providers (overridable in tests)
# --------------------------------------------------------------------------- #
@lru_cache
def _employee_service_singleton() -> EmployeeService:
    return EmployeeService(StorageService(get_settings().data_file))


@lru_cache
def _external_client_singleton() -> ExternalAPIClient:
    settings = get_settings()
    return ExternalAPIClient(
        base_url=settings.external_api_url,
        timeout=settings.external_api_timeout,
        default_salary=settings.default_salary,
    )


def get_employee_service() -> EmployeeService:
    return _employee_service_singleton()


def get_external_client() -> ExternalAPIClient:
    return _external_client_singleton()


def get_file_processor() -> FileProcessor:
    return FileProcessor()


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
@router.get("/employees", response_model=EmployeePage, tags=["employees"])
def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    department: Optional[str] = Query(None, description="Filter by department (case-insensitive)"),
    service: EmployeeService = Depends(get_employee_service),
) -> EmployeePage:
    return service.list_employees(page=page, page_size=page_size, department=department)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse, tags=["employees"])
def get_employee(
    employee_id: int, service: EmployeeService = Depends(get_employee_service)
):
    return service.get_employee(employee_id)


@router.post("/employees", response_model=EmployeeResponse, status_code=201, tags=["employees"])
def create_employee(
    payload: EmployeeCreate, service: EmployeeService = Depends(get_employee_service)
):
    return service.create_employee(payload)


@router.put("/employees/{employee_id}", response_model=EmployeeResponse, tags=["employees"])
def replace_employee(
    employee_id: int,
    payload: EmployeeCreate,
    service: EmployeeService = Depends(get_employee_service),
):
    return service.replace_employee(employee_id, payload)


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse, tags=["employees"])
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    service: EmployeeService = Depends(get_employee_service),
):
    return service.update_employee(employee_id, payload)


@router.delete("/employees/{employee_id}", status_code=204, tags=["employees"])
def delete_employee(
    employee_id: int, service: EmployeeService = Depends(get_employee_service)
) -> None:
    service.delete_employee(employee_id)


# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
async def _read_upload(file: UploadFile, allowed_extensions: Tuple[str, ...]) -> bytes:
    filename = (file.filename or "").lower()
    if not filename.endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    return content


async def _handle_import(
    file: UploadFile,
    allowed_extensions: Tuple[str, ...],
    parser: Callable[[bytes], List[Dict[str, str]]],
    service: EmployeeService,
) -> ImportResult:
    content = await _read_upload(file, allowed_extensions)
    try:
        rows = await run_in_threadpool(parser, content)
    except FileProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await run_in_threadpool(service.bulk_create, rows)


@router.post("/employees/import/csv", response_model=ImportResult, tags=["import"])
async def import_csv(
    file: UploadFile = File(...),
    service: EmployeeService = Depends(get_employee_service),
    processor: FileProcessor = Depends(get_file_processor),
) -> ImportResult:
    return await _handle_import(file, (".csv",), processor.parse_csv, service)


@router.post("/employees/import/excel", response_model=ImportResult, tags=["import"])
async def import_excel(
    file: UploadFile = File(...),
    service: EmployeeService = Depends(get_employee_service),
    processor: FileProcessor = Depends(get_file_processor),
) -> ImportResult:
    return await _handle_import(file, (".xlsx", ".xlsm"), processor.parse_excel, service)


@router.post("/employees/import/pdf", response_model=ImportResult, tags=["import"])
async def import_pdf(
    file: UploadFile = File(...),
    service: EmployeeService = Depends(get_employee_service),
    processor: FileProcessor = Depends(get_file_processor),
) -> ImportResult:
    return await _handle_import(file, (".pdf",), processor.parse_pdf, service)


# --------------------------------------------------------------------------- #
# External sync
# --------------------------------------------------------------------------- #
@log_execution
def run_sync(client: ExternalAPIClient, service: EmployeeService) -> None:
    """Background job: pull employees from the external API and import them."""
    try:
        rows = client.fetch_employees()
    except ExternalAPIError:
        logger.exception("External sync failed")
        return
    result = service.bulk_create(rows)
    logger.info(
        "External sync finished: total=%s imported=%s skipped=%s",
        result.total,
        result.imported,
        result.skipped,
    )


@router.post("/employees/sync", response_model=MessageResponse, status_code=202, tags=["sync"])
def sync_employees(
    background_tasks: BackgroundTasks,
    service: EmployeeService = Depends(get_employee_service),
    client: ExternalAPIClient = Depends(get_external_client),
) -> MessageResponse:
    background_tasks.add_task(run_sync, client, service)
    return MessageResponse(status="accepted", detail="Employee sync started in the background")