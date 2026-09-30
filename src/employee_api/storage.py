"""JSON file persistence with thread-safe, atomic read-modify-write operations."""

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List

from employee_api.utils.logger import get_logger

logger = get_logger(__name__)

Record = Dict[str, Any]


class StorageError(RuntimeError):
    """Raised when the underlying data file cannot be read or written."""


class StorageService:
    """Stores employee records in a single JSON file (data/employees.json)."""

    def __init__(self, file_path: Path) -> None:
        self._path = Path(file_path)
        self._lock = threading.RLock()
        self._ensure_file()

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_file(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._write([])
                logger.info("Created data file at %s", self._path)

    def _read(self) -> List[Record]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise StorageError(f"Unable to read data file: {exc}") from exc

        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StorageError(f"Data file is corrupted: {exc}") from exc
        if not isinstance(data, list):
            raise StorageError("Data file must contain a JSON array")
        return data

    def _write(self, records: List[Record]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp_path.replace(self._path)
        except OSError as exc:
            raise StorageError(f"Unable to write data file: {exc}") from exc

    def read_all(self) -> List[Record]:
        with self._lock:
            return self._read()

    def write_all(self, records: List[Record]) -> None:
        with self._lock:
            self._write(records)

    @contextmanager
    def transaction(self) -> Iterator[List[Record]]:
        """Yield the records list; changes are persisted only if the block succeeds."""
        with self._lock:
            records = self._read()
            yield records
            self._write(records)