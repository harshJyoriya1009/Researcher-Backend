"""
Domain exceptions. Services raise these; the global exception handler
middleware (app/middleware/error_handler.py) translates them into
consistent JSON error responses.
"""


class AppError(Exception):
    """Base class for all application (non-framework) errors."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str | None = None):
        self.message = message or "An unexpected error occurred."
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class AlreadyExistsError(AppError):
    status_code = 409
    error_code = "already_exists"


class InvalidCredentialsError(AppError):
    status_code = 401
    error_code = "invalid_credentials"

    def __init__(self, message: str | None = None):
        super().__init__(message or "Incorrect email or password.")


class UnauthorizedError(AppError):
    status_code = 401
    error_code = "unauthorized"

    def __init__(self, message: str | None = None):
        super().__init__(message or "Authentication required.")


class ForbiddenError(AppError):
    status_code = 403
    error_code = "forbidden"


class ValidationFailedError(AppError):
    status_code = 422
    error_code = "validation_failed"


class GuardrailViolationError(AppError):
    """Raised when a generated response fails a safety/grounding check."""

    status_code = 422
    error_code = "guardrail_violation"


class LLMProviderError(AppError):
    status_code = 502
    error_code = "llm_provider_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or "The language model provider returned an error.")


class DocumentProcessingError(AppError):
    status_code = 422
    error_code = "document_processing_error"


class RateLimitExceededError(AppError):
    status_code = 429
    error_code = "rate_limit_exceeded"

    def __init__(self, message: str | None = None):
        super().__init__(message or "Too many requests. Please slow down.")
