"""Application configuration loaded from environment variables (.env supported)."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from employee_api import __version__

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    log_level: str
    log_file: Path
    data_file: Path
    webhook_secret: str
    external_api_url: str
    external_api_timeout: float
    default_salary: float
    max_upload_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "Mini Employee Directory API"),
            app_version=__version__,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=_resolve_path(os.getenv("LOG_FILE", "logs/app.log")),
            data_file=_resolve_path(os.getenv("DATA_FILE", "data/employees.json")),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            external_api_url=os.getenv("EXTERNAL_API_URL", "https://dummyjson.com/users?limit=30"),
            external_api_timeout=float(os.getenv("EXTERNAL_API_TIMEOUT", "10")),
            default_salary=float(os.getenv("DEFAULT_SALARY", "50000")),
            max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()