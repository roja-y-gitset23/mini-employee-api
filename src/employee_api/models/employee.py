"""Domain model representing a persisted employee record."""

from datetime import datetime

from pydantic import BaseModel


class Employee(BaseModel):
    id: int
    name: str
    email: str
    department: str
    position: str
    salary: float
    created_at: datetime
    updated_at: datetime