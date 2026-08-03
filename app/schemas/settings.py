from pydantic import BeforeValidator, Field
from typing import Annotated

from app.agents.llm.provider import AVAILABLE_MODELS
from app.schemas.common import InputSchema

_ALLOWED_MODEL_IDS = {model["id"] for model in AVAILABLE_MODELS}


def _validate_model_id(value: str) -> str:
    if value not in _ALLOWED_MODEL_IDS:
        raise ValueError(f"Unknown model id: {value}")
    return value


ModelId = Annotated[str, BeforeValidator(_validate_model_id)]


class ModelOption(InputSchema):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=500)
    configured: bool = True


class ModelListResponse(InputSchema):
    models: list[ModelOption]
    current_model: str = Field(min_length=1, max_length=128)


class ModelUpdateRequest(InputSchema):
    model: ModelId
