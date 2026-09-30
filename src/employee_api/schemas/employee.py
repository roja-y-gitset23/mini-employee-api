"""Pydantic request/response schemas for employees.

Email uniqueness is enforced in EmployeeService (requires access to stored data).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    position: str = Field(min_length=1, max_length=100)
    salary: float = Field(gt=0, description="Must be a positive number")

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return str(value).strip().lower()


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    position: Optional[str] = Field(default=None, min_length=1, max_length=100)
    salary: Optional[float] = Field(default=None, gt=0)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: Optional[str]) -> Optional[str]:
        return str(value).strip().lower() if value is not None else value

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "EmployeeUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    department: str
    position: str
    salary: float
    created_at: datetime
    updated_at: datetime


class EmployeePage(BaseModel):
    items: List[EmployeeResponse]
    total: int
    page: int
    page_size: int
    pages: int