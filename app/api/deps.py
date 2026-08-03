from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limits import RedisRateLimiter, get_client_ip
from app.database.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    return await AuthService(db).get_current_user(token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def user_action_rate_limit(*, scope: str, limit: int, window_seconds: int):
    async def dependency(current_user: CurrentUser) -> None:
        limiter = RedisRateLimiter()
        await limiter.enforce_fixed_window(
            scope=scope,
            identifier=str(current_user.id),
            limit=limit,
            window_seconds=window_seconds,
            message="You are sending too many requests for this action.",
        )

    return dependency


def ip_rate_limit(*, scope: str, limit: int, window_seconds: int):
    async def dependency(request: Request) -> None:
        limiter = RedisRateLimiter()
        await limiter.enforce_fixed_window(
            scope=scope,
            identifier=get_client_ip(request),
            limit=limit,
            window_seconds=window_seconds,
            message="Too many requests from this client.",
        )

    return dependency
