import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.logging import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        logger.info(f"[{request_id}] --> {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(f"[{request_id}] <-- {request.method} {request.url.path} failed after {duration_ms:.1f}ms")
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"[{request_id}] <-- {request.method} {request.url.path} "
            f"{response.status_code} in {duration_ms:.1f}ms"
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.1f}"
        return response
