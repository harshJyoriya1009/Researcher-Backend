"""
Loguru configuration. Call `configure_logging()` once at startup.
"""
import sys

from loguru import logger

from app.core.config import settings


def configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
    )
    if settings.is_production:
        logger.add(
            "logs/app.log",
            level="INFO",
            rotation="50 MB",
            retention="14 days",
            compression="zip",
            serialize=True,
        )


__all__ = ["logger", "configure_logging"]
