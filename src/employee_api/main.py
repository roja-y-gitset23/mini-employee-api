"""FastAPI application factory and entrypoint."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from employee_api.api import routes, webhooks
from employee_api.config import get_settings
from employee_api.services.employee_service import (
    DuplicateEmailError,
    EmployeeNotFoundError,
)
from employee_api.services.external_api_service import ExternalAPIError
from employee_api.services.file_service import FileProcessingError
from employee_api.storage import StorageError
from employee_api.utils.logger import get_logger, setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    logger = get_logger(__name__)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Employee directory with CRUD, file imports, external sync and webhooks.",
    )
    app.include_router(routes.router)
    app.include_router(webhooks.router)

    @app.exception_handler(EmployeeNotFoundError)
    async def _not_found(_: Request, exc: EmployeeNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DuplicateEmailError)
    async def _duplicate(_: Request, exc: DuplicateEmailError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(FileProcessingError)
    async def _file_error(_: Request, exc: FileProcessingError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ExternalAPIError)
    async def _external_error(_: Request, exc: ExternalAPIError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(StorageError)
    async def _storage_error(_: Request, exc: StorageError) -> JSONResponse:
        logger.error("Storage failure: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Storage failure"})

    logger.info("Application '%s' v%s initialised", settings.app_name, settings.app_version)
    return app


app = create_app()