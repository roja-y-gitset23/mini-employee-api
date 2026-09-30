"""Shared response schemas."""

from datetime import datetime
from typing import List

from pydantic import BaseModel


class MessageResponse(BaseModel):
    status: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    total: int
    imported: int
    skipped: int
    errors: List[ImportRowError]