"""
Password hashing and JWT helpers. No business logic lives here —
this module only knows about cryptography, not users or sessions.
"""
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError as JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str | UUID, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type.value,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str | UUID) -> str:
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str | UUID) -> str:
    return _create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_password_reset_token(user_id: str | UUID) -> str:
    return _create_token(
        user_id,
        TokenType.PASSWORD_RESET,
        timedelta(minutes=30),
    )


def create_email_verification_token(user_id: str | UUID) -> str:
    return _create_token(
        user_id,
        TokenType.EMAIL_VERIFICATION,
        timedelta(hours=24),
    )


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired, or the wrong type."""


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Token is invalid or expired.") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token.")

    return payload


def seconds_until_expiry(payload: dict[str, Any]) -> int:
    """Seconds remaining until this token's `exp` claim, floored at 0."""
    exp = payload.get("exp")
    if exp is None:
        return 0
    exp_dt = datetime.fromtimestamp(exp, tz=UTC)
    remaining = (exp_dt - datetime.now(UTC)).total_seconds()
    return max(0, int(remaining))
