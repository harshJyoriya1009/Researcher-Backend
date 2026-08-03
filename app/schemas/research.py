from uuid import UUID

from typing import Annotated

from pydantic import BeforeValidator, Field

from app.models.message import MessageRole
from app.agents.llm.provider import AVAILABLE_MODELS
from app.schemas.common import InputSchema, TimestampedSchema

_ALLOWED_MODEL_IDS = {model["id"] for model in AVAILABLE_MODELS}


def _validate_model_id(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in _ALLOWED_MODEL_IDS:
        raise ValueError(f"Unknown model id: {value}")
    return value


ModelId = Annotated[str, BeforeValidator(_validate_model_id)]


class CitationRead(InputSchema):
    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    url: str = Field(min_length=1, max_length=2048)
    snippet: str | None = Field(default=None, max_length=2000)


class MessageRead(TimestampedSchema):
    session_id: UUID
    role: MessageRole
    content: str = Field(min_length=1, max_length=8000)
    citations: list[CitationRead] | None = None
    error: str | None = Field(default=None, max_length=2000)


class SessionRead(TimestampedSchema):
    title: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=128)
    pinned: bool
    message_count: int = 0


class SessionDetail(InputSchema):
    session: SessionRead
    messages: list[MessageRead]


class SessionCreateRequest(InputSchema):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S(?:.*\S)?$",
    )
    model: ModelId | None = None


class SessionRenameRequest(InputSchema):
    title: str = Field(min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")


class ChatRequest(InputSchema):
    session_id: UUID | None = None
    content: str = Field(min_length=1, max_length=8000)
    model: ModelId | None = None
    document_ids: list[UUID] | None = Field(default=None, max_length=100)


class ChatResponse(InputSchema):
    session_id: UUID
    message: MessageRead
