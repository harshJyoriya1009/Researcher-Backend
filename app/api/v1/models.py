from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, user_action_rate_limit
from app.core.config import settings
from app.schemas.settings import ModelListResponse, ModelUpdateRequest
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/models", tags=["Settings"])


@router.get("", response_model=ModelListResponse)
async def list_models(
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="models:read",
            limit=settings.RATE_LIMIT_READ_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> ModelListResponse:
    return SettingsService(db).list_models(current_user)


@router.put("", response_model=ModelListResponse)
async def update_model(
    payload: ModelUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="models:write",
            limit=settings.RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> ModelListResponse:
    return await SettingsService(db).update_model(current_user, payload.model)
