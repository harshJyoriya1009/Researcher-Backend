"""
Global exception handlers. Registered once in app.main so every route
returns a consistent error envelope regardless of where the failure
originated (domain service, Pydantic validation, or SQLAlchemy).
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import logger


def _error_body(error_code: str, message: str) -> dict:
    body = {"error": error_code, "message": message}
    return body


def _safe_http_message(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "Authentication required."
    if status_code == status.HTTP_403_FORBIDDEN:
        return "You do not have permission to perform this action."
    if status_code == status.HTTP_404_NOT_FOUND:
        return "The requested resource was not found."
    if status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        return "That action is not allowed."
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return "Too many requests. Please try again later."
    return "The request could not be completed."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(f"{exc.error_code} on {request.method} {request.url.path}: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.error_code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            f"validation_failed on {request.method} {request.url.path}: {exc.errors()}"
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_failed", "Your request could not be processed."),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning(
            f"http_error {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", _safe_http_message(exc.status_code)),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.exception(f"Database integrity error on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_body("integrity_error", "The request could not be completed."),
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception(f"Database error on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("database_error", "A server error occurred."),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled error on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "An unexpected error occurred."),
        )
