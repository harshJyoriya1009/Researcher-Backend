from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, ip_rate_limit, oauth2_scheme, user_action_rate_limit
from app.core.config import settings
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LinkedAccountsResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
    TokenPair,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:register",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> AuthResponse:
    return await AuthService(db).register(payload.name, payload.email, payload.password)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:login",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> AuthResponse:
    return await AuthService(db).login(payload.email, payload.password)


@router.post("/google", response_model=AuthResponse)
async def google_login(
    payload: GoogleAuthRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:google",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> AuthResponse:
    return await AuthService(db).login_with_google(payload.credential)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:refresh",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> TokenPair:
    return await AuthService(db).refresh(payload.refresh_token)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:forgot-password",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).request_password_reset(payload.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:reset-password",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).reset_password(payload.token, payload.new_password)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
    payload: VerifyEmailRequest,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:verify-email",
            limit=settings.RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).verify_email(payload.token)


@router.get("/linked-accounts", response_model=LinkedAccountsResponse)
async def linked_accounts(
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:read",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> LinkedAccountsResponse:
    return await AuthService(db).get_linked_accounts(current_user)


@router.post("/link/google", status_code=status.HTTP_204_NO_CONTENT)
async def link_google_account(
    payload: GoogleAuthRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:write",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).link_google_account(current_user, payload.credential)


@router.delete("/link/google", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_google_account(
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:write",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).unlink_google_account(current_user)


@router.post("/set-password", status_code=status.HTTP_204_NO_CONTENT)
async def set_password(
    payload: SetPasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:write",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).set_initial_password(current_user, payload.new_password)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:read",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await AuthService(db).resend_verification_email(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: DbSession,
    access_token: str = Depends(oauth2_scheme),
    payload: RefreshRequest | None = None,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:write",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    refresh_token = payload.refresh_token if payload else None
    await AuthService(db).logout(access_token, refresh_token)


@router.get("/me", response_model=UserRead)
async def me(
    current_user: CurrentUser,
    _: None = Depends(
        ip_rate_limit(
            scope="auth:management",
            limit=settings.RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE,
            window_seconds=60,
        )
    ),
    __: None = Depends(
        user_action_rate_limit(
            scope="auth:read",
            limit=settings.RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> UserRead:
    return UserRead.model_validate(current_user)
