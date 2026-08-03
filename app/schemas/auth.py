from pydantic import EmailStr, Field

from app.schemas.common import InputSchema

from app.schemas.user import UserRead


class RegisterRequest(InputSchema):
    name: str = Field(min_length=2, max_length=255, pattern=r"^\S(?:.*\S)?$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, pattern=r"^\S(?:.*\S)?$")


class LoginRequest(InputSchema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")


class RefreshRequest(InputSchema):
    refresh_token: str = Field(min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9._-]+$")


class ForgotPasswordRequest(InputSchema):
    email: EmailStr


class ResetPasswordRequest(InputSchema):
    token: str = Field(min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9._-]+$")
    new_password: str = Field(min_length=8, max_length=128, pattern=r"^\S(?:.*\S)?$")


class VerifyEmailRequest(InputSchema):
    token: str = Field(min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9._-]+$")


class GoogleAuthRequest(InputSchema):
    credential: str = Field(min_length=1, max_length=8192, pattern=r"^[A-Za-z0-9._-]+$")


class SetPasswordRequest(InputSchema):
    new_password: str = Field(min_length=8, max_length=128, pattern=r"^\S(?:.*\S)?$")


class LinkedAccount(InputSchema):
    provider: str
    email: str
    linked_at: str


class LinkedAccountsResponse(InputSchema):
    has_password: bool
    linked_accounts: list[LinkedAccount]


class TokenPair(InputSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(TokenPair):
    user: UserRead
