from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsError,
    InvalidCredentialsError,
    NotFoundError,
    UnauthorizedError,
    ValidationFailedError,
)
from app.core.config import settings
from app.core.email_templates import render_email
from app.core.google_auth import verify_google_id_token
from app.core.email import send_email
from app.core.rate_limits import RedisRateLimiter
from app.core.redis_client import get_redis_client
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    create_password_reset_token,
    decode_token,
    hash_password,
    seconds_until_expiry,
    verify_password,
)
from app.core.logging import logger
from app.models.user import User
from app.repositories.oauth_account_repository import OAuthAccountRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthResponse, LinkedAccount, LinkedAccountsResponse, TokenPair
from app.schemas.user import UserRead


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis | None = None):
        self.session = session
        self.users = UserRepository(session)
        self.oauth_accounts = OAuthAccountRepository(session)
        self.redis = redis or get_redis_client()
        self.rate_limiter = RedisRateLimiter(self.redis)

    def _revocation_key(self, jti: str) -> str:
        return f"revoked_token:{jti}"

    # Every authenticated request pays one Redis lookup so logout/revocation is immediate.
    async def _is_revoked(self, jti: str | None) -> bool:
        if not jti:
            return False
        return bool(await self.redis.exists(self._revocation_key(jti)))

    async def _revoke_payload(self, payload: dict[str, Any]) -> None:
        jti = payload.get("jti")
        ttl = seconds_until_expiry(payload)
        if jti and ttl > 0:
            await self.redis.set(self._revocation_key(str(jti)), "1", ex=ttl)

    async def _send_rendered_email(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        try:
            await send_email(to=to, subject=subject, body=text_body, html_body=html_body)
        except TypeError:
            # Backward compatibility for tests or local monkeypatches that still
            # replace send_email with the older 3-argument signature.
            await send_email(to, subject, text_body)

    async def _ensure_auth_backoff_clear(self, scope: str, identifiers: list[str]) -> None:
        for identifier in identifiers:
            await self.rate_limiter.ensure_backoff_clear(scope=scope, identifier=identifier)

    async def _record_auth_failure(self, scope: str, identifiers: list[str]) -> None:
        for identifier in identifiers:
            await self.rate_limiter.record_backoff_failure(
                scope=scope,
                identifier=identifier,
                window_seconds=settings.RATE_LIMIT_AUTH_FAILURE_WINDOW_SECONDS,
                base_delay_seconds=settings.RATE_LIMIT_AUTH_FAILURE_BACKOFF_BASE_SECONDS,
                max_delay_seconds=settings.RATE_LIMIT_AUTH_FAILURE_BACKOFF_MAX_SECONDS,
            )

    async def _clear_auth_backoff(self, scope: str, identifiers: list[str]) -> None:
        for identifier in identifiers:
            await self.rate_limiter.clear_backoff_state(scope=scope, identifier=identifier)

    async def register(self, name: str, email: str, password: str, request_ip: str | None = None) -> AuthResponse:
        email_key = email.lower()
        identifiers = [f"ip:{request_ip}"] if request_ip else []
        identifiers.append(f"email:{email_key}")
        await self._ensure_auth_backoff_clear("register", identifiers)

        existing = await self.users.get_by_email(email)
        if existing:
            await self._record_auth_failure("register", identifiers)
            raise AlreadyExistsError("An account with this email already exists.")

        user = await self.users.create(
            name=name,
            email=email_key,
            hashed_password=hash_password(password),
        )
        await self.session.commit()

        await self._clear_auth_backoff("register", identifiers)
        await self._send_verification_email(user)

        return self._issue_tokens(user)

    async def login(self, email: str, password: str, request_ip: str | None = None) -> AuthResponse:
        email_key = email.lower()
        identifiers = [f"ip:{request_ip}"] if request_ip else []
        identifiers.append(f"email:{email_key}")
        await self._ensure_auth_backoff_clear("login", identifiers)

        user = await self.users.get_by_email(email)
        if not user:
            await self._record_auth_failure("login", identifiers)
            raise InvalidCredentialsError()
        if not user.hashed_password:
            await self._record_auth_failure("login", identifiers)
            raise InvalidCredentialsError(
                "This account uses Google sign-in. Continue with Google or set a password from Settings."
            )
        if not verify_password(password, user.hashed_password):
            await self._record_auth_failure("login", identifiers)
            raise InvalidCredentialsError()
        if not user.is_active:
            await self._record_auth_failure("login", identifiers)
            raise UnauthorizedError("This account has been deactivated.")

        await self._clear_auth_backoff("login", identifiers)
        return self._issue_tokens(user)

    async def login_with_google(self, credential: str, request_ip: str | None = None) -> AuthResponse:
        payload = verify_google_id_token(credential)
        email = str(payload.get("email", "")).lower()
        provider_account_id = str(payload.get("sub", ""))
        display_name = str(payload.get("name") or payload.get("given_name") or email.split("@")[0])
        identifiers = [f"ip:{request_ip}"] if request_ip else []
        if email:
            identifiers.append(f"email:{email}")

        if not email or not provider_account_id:
            if identifiers:
                await self._record_auth_failure("google", identifiers)
            raise UnauthorizedError("Google sign-in did not return the required profile details.")

        await self._ensure_auth_backoff_clear("google", identifiers)

        linked_account = await self.oauth_accounts.get_by_provider_account("google", provider_account_id)
        if linked_account:
            user = await self.users.get_by_id(linked_account.user_id)
            if not user:
                # The user row was deleted but the OAuth link survived. Clean it up so the
                # Google account can be re-created or linked again on this login attempt.
                await self.oauth_accounts.delete(linked_account)
                await self.session.commit()
                linked_account = None
            elif not user.is_active:
                await self._record_auth_failure("google", identifiers)
                raise UnauthorizedError("This account has been deactivated.")
            else:
                await self._clear_auth_backoff("google", identifiers)
                return self._issue_tokens(user)

        existing_user = await self.users.get_by_email(email)
        if existing_user:
            if not existing_user.is_active:
                await self._record_auth_failure("google", identifiers)
                raise UnauthorizedError("This account has been deactivated.")
            if not existing_user.is_verified:
                await self._record_auth_failure("google", identifiers)
                raise AlreadyExistsError(
                    "This email is already registered with a password account. Please sign in with email/password first."
                )
            existing_link = await self.oauth_accounts.get_for_user(existing_user.id, "google")
            if not existing_link:
                await self.oauth_accounts.create(
                    user_id=existing_user.id,
                    provider="google",
                    provider_account_id=provider_account_id,
                    email=email,
                )
                await self.session.commit()
            await self._clear_auth_backoff("google", identifiers)
            return self._issue_tokens(existing_user)

        user = await self.users.create(
            name=display_name,
            email=email,
            hashed_password=None,
            is_verified=True,
        )
        await self.oauth_accounts.create(
            user_id=user.id,
            provider="google",
            provider_account_id=provider_account_id,
            email=email,
        )
        await self.session.commit()
        await self._clear_auth_backoff("google", identifiers)
        return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            logger.warning(f"Invalid refresh token: {exc}")
            raise UnauthorizedError("Your session is invalid or expired.") from exc

        if await self._is_revoked(payload.get("jti")):
            raise UnauthorizedError("This session has been logged out.")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if not user or not user.is_active:
            raise UnauthorizedError("User no longer exists or is inactive.")

        await self._revoke_payload(payload)

        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def get_current_user(self, access_token: str) -> User:
        try:
            payload = decode_token(access_token, TokenType.ACCESS)
        except InvalidTokenError as exc:
            logger.warning(f"Invalid access token: {exc}")
            raise UnauthorizedError("Authentication required.") from exc

        if await self._is_revoked(payload.get("jti")):
            raise UnauthorizedError("This session has been logged out.")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if not user:
            raise NotFoundError("User not found.")
        if not user.is_active:
            raise UnauthorizedError("This account has been deactivated.")
        return user

    async def request_password_reset(self, email: str, request_ip: str | None = None) -> None:
        email_key = email.lower()
        identifiers = [f"ip:{request_ip}"] if request_ip else []
        identifiers.append(f"email:{email_key}")
        await self._ensure_auth_backoff_clear("forgot_password", identifiers)

        user = await self.users.get_by_email(email)
        if not user:
            await self._record_auth_failure("forgot_password", identifiers)
            return
        token = create_password_reset_token(user.id)
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        content = render_email(
            subject="Reset your password",
            recipient_name=user.name,
            heading="Reset your password",
            paragraphs=[
                "We received a request to reset your password.",
                "This link will expire in 30 minutes for your security.",
            ],
            cta_text="Reset password",
            cta_url=reset_link,
            footer_note=(
                "If you didn't request this, you can safely ignore this email — your password "
                "won't be changed."
            ),
        )
        await self._send_rendered_email(
            to=user.email,
            subject=content.subject,
            text_body=content.text_body,
            html_body=content.html_body,
        )
        await self._clear_auth_backoff("forgot_password", identifiers)

    async def reset_password(self, token: str, new_password: str, request_ip: str | None = None) -> None:
        try:
            payload = decode_token(token, TokenType.PASSWORD_RESET)
        except InvalidTokenError as exc:
            if request_ip:
                await self._record_auth_failure("reset_password", [f"ip:{request_ip}"])
            logger.warning(f"Invalid password reset token: {exc}")
            raise UnauthorizedError("This password reset link is invalid or expired.") from exc

        identifiers = [f"ip:{request_ip}"] if request_ip else []
        user_id = str(payload.get("sub", ""))
        if user_id:
            identifiers.append(f"user:{user_id}")
        await self._ensure_auth_backoff_clear("reset_password", identifiers)

        if await self._is_revoked(payload.get("jti")):
            await self._record_auth_failure("reset_password", identifiers)
            raise UnauthorizedError("This password reset link has already been used.")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if not user:
            await self._record_auth_failure("reset_password", identifiers)
            raise UnauthorizedError("User no longer exists.")

        await self.users.update(user, hashed_password=hash_password(new_password))
        await self.session.commit()
        await self._revoke_payload(payload)
        await self._clear_auth_backoff("reset_password", identifiers)

    async def verify_email(self, token: str, request_ip: str | None = None) -> None:
        try:
            payload = decode_token(token, TokenType.EMAIL_VERIFICATION)
        except InvalidTokenError as exc:
            if request_ip:
                await self._record_auth_failure("verify_email", [f"ip:{request_ip}"])
            logger.warning(f"Invalid email verification token: {exc}")
            raise UnauthorizedError("This verification link is invalid or expired.") from exc

        identifiers = [f"ip:{request_ip}"] if request_ip else []
        user_id = str(payload.get("sub", ""))
        if user_id:
            identifiers.append(f"user:{user_id}")
        await self._ensure_auth_backoff_clear("verify_email", identifiers)

        if await self._is_revoked(payload.get("jti")):
            await self._record_auth_failure("verify_email", identifiers)
            raise UnauthorizedError("This verification link has already been used.")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if not user:
            await self._record_auth_failure("verify_email", identifiers)
            raise UnauthorizedError("User no longer exists.")

        await self.users.update(user, is_verified=True)
        await self.session.commit()
        await self._revoke_payload(payload)
        await self._clear_auth_backoff("verify_email", identifiers)

    async def link_google_account(self, current_user: User, credential: str) -> None:
        payload = verify_google_id_token(credential)
        email = str(payload.get("email", "")).lower()
        provider_account_id = str(payload.get("sub", ""))

        if not email or not provider_account_id:
            raise UnauthorizedError("Google sign-in did not return the required profile details.")

        existing_link = await self.oauth_accounts.get_by_provider_account("google", provider_account_id)
        if existing_link and existing_link.user_id != current_user.id:
            raise AlreadyExistsError("That Google account is already linked to another user.")
        if existing_link and existing_link.user_id == current_user.id:
            raise AlreadyExistsError("You already have this Google account linked.")

        current_user_link = await self.oauth_accounts.get_for_user(current_user.id, "google")
        if current_user_link:
            raise AlreadyExistsError("You already have a Google account linked.")

        await self.oauth_accounts.create(
            user_id=current_user.id,
            provider="google",
            provider_account_id=provider_account_id,
            email=email,
        )
        await self.session.commit()

        content = render_email(
            subject="A Google account was linked to your account",
            recipient_name=current_user.name,
            heading="New sign-in method added",
            paragraphs=[
                (
                    f"A Google account ({email}) was just linked to your account, allowing "
                    "sign-in with Google going forward."
                ),
            ],
            footer_note=(
                "If this wasn't you, reset your password immediately — someone may have access "
                "to your account."
            ),
        )
        await self._send_rendered_email(
            to=current_user.email,
            subject=content.subject,
            text_body=content.text_body,
            html_body=content.html_body,
        )

    async def unlink_google_account(self, current_user: User) -> None:
        current_user_link = await self.oauth_accounts.get_for_user(current_user.id, "google")
        if not current_user_link:
            raise NotFoundError("No Google account is linked to this profile.")
        if not current_user.hashed_password:
            raise ValidationFailedError("Set a password before unlinking Google sign-in.")

        await self.oauth_accounts.delete(current_user_link)
        await self.session.commit()

        content = render_email(
            subject="A Google account was unlinked from your account",
            recipient_name=current_user.name,
            heading="Sign-in method removed",
            paragraphs=[
                "A Google account was just unlinked from your account. You can still sign in with your password.",
            ],
            footer_note=(
                "If this wasn't you, reset your password immediately — someone may have access "
                "to your account."
            ),
        )
        await self._send_rendered_email(
            to=current_user.email,
            subject=content.subject,
            text_body=content.text_body,
            html_body=content.html_body,
        )

    async def get_linked_accounts(self, current_user: User) -> LinkedAccountsResponse:
        accounts = await self.oauth_accounts.list_for_user(current_user.id)
        return LinkedAccountsResponse(
            has_password=bool(current_user.hashed_password),
            linked_accounts=[
                LinkedAccount(
                    provider=account.provider,
                    email=account.email,
                    linked_at=account.created_at.isoformat(),
                )
                for account in accounts
            ],
        )

    async def set_initial_password(self, current_user: User, new_password: str) -> None:
        if current_user.hashed_password:
            raise ValidationFailedError(
                "This account already has a password. Use the change-password flow instead."
            )

        await self.users.update(current_user, hashed_password=hash_password(new_password))
        await self.session.commit()

    async def resend_verification_email(self, user: User) -> None:
        if user.is_verified:
            return
        await self._send_verification_email(user)

    async def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        try:
            access_payload = decode_token(access_token, TokenType.ACCESS)
            await self._revoke_payload(access_payload)
        except InvalidTokenError:
            pass

        if refresh_token:
            try:
                refresh_payload = decode_token(refresh_token, TokenType.REFRESH)
                await self._revoke_payload(refresh_payload)
            except InvalidTokenError:
                pass

    async def _send_verification_email(self, user: User) -> None:
        token = create_email_verification_token(user.id)
        verify_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        content = render_email(
            subject="Verify your email",
            recipient_name=user.name,
            heading="Confirm your email address",
            paragraphs=[
                f"Welcome to {settings.APP_NAME} — please confirm this is your email address.",
                "You can use the app before verifying, but we recommend confirming soon.",
            ],
            cta_text="Verify email",
            cta_url=verify_link,
        )
        await self._send_rendered_email(
            to=user.email,
            subject=content.subject,
            text_body=content.text_body,
            html_body=content.html_body,
        )

    def _issue_tokens(self, user: User) -> AuthResponse:
        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserRead.model_validate(user),
        )
