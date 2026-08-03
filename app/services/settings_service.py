from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm.provider import AVAILABLE_MODELS, get_available_models
from app.core.exceptions import ValidationFailedError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.settings import ModelListResponse, ModelOption


class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    def list_models(self, current_user: User) -> ModelListResponse:
        return ModelListResponse(
            models=[ModelOption(**m) for m in get_available_models()],
            current_model=current_user.default_model,
        )

    async def update_model(self, current_user: User, model_id: str) -> ModelListResponse:
        valid_ids = {m["id"] for m in AVAILABLE_MODELS}
        if model_id not in valid_ids:
            raise ValidationFailedError(f"Unknown model id: {model_id}")

        await self.users.update(current_user, default_model=model_id)
        await self.session.commit()

        return self.list_models(current_user)
