from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import sentry_sdk

from app import models  # noqa: F401
from app.api.deps import ip_rate_limit
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core.logging import configure_logging, logger
from app.database.session import AsyncSessionLocal
from app.middleware.error_handler import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=settings.APP_ENV,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(f"Starting {settings.APP_NAME} ({settings.APP_ENV})")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Modular-monolith backend for an AI research assistant: JWT auth, "
    "LangGraph-orchestrated RAG chat, document ingestion, and streaming responses.",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request logging ---
app.add_middleware(RequestLoggingMiddleware)

# --- Global exception handling ---
register_exception_handlers(app)

# --- Routes ---
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Health"])
async def health_check(
    _: None = Depends(
        ip_rate_limit(
            scope="health",
            limit=settings.RATE_LIMIT_PUBLIC_ENDPOINTS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> dict:
    checks = {"database": "ok", "redis": "ok"}
    overall = "ok"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"
        overall = "degraded"

    try:
        redis_client = get_redis_client()
        await redis_client.ping()
    except Exception:
        checks["redis"] = "unavailable"
        overall = "degraded"

    return {
        "status": overall,
        "app": settings.APP_NAME,
        "checks": checks,
    }
