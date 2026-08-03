from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for schemas that read directly from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class InputSchema(BaseModel):
    """Base for inbound request schemas.

    We forbid extra fields so requests must match the declared contract exactly.
    """

    model_config = ConfigDict(extra="forbid")


class TimestampedSchema(ORMBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    message: str


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool
