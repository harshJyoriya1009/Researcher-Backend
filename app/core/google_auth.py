from __future__ import annotations

from typing import Any
from app.core.logging import logger

from google.auth.transport.requests import Request
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.exceptions import AppError, UnauthorizedError


class GoogleSignInNotConfiguredError(AppError):
    status_code = 503
    error_code = "google_signin_not_configured"

    def __init__(self) -> None:
        super().__init__("Google sign-in is not configured.")


def verify_google_id_token(token: str) -> dict[str, Any]:
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleSignInNotConfiguredError()

    try:
        payload = google_id_token.verify_oauth2_token(
            token,
            Request(),
            audience=settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=settings.GOOGLE_OAUTH_CLOCK_SKEW_SECONDS,
        )
    except ValueError as exc:
        logger.error(f"Google token verification actually failed: {exc}")
        raise UnauthorizedError("Google sign-in failed. Please try again.") from exc

    if not payload.get("email_verified"):
        raise UnauthorizedError("Your Google email address is not verified.")

    return payload
