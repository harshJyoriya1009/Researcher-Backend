"""
Centralized application configuration.

All environment-derived settings live here so the rest of the codebase
never touches `os.environ` directly. Import `settings` wherever config
is needed.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "Researcher"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLOCK_SKEW_SECONDS: int = 60
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    SENTRY_DSN: str = ""

    # --- Email (SMTP) ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Researcher"
    SMTP_USE_TLS: bool = True

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://research_user@localhost:5432/research_assistant"
    )
    DATABASE_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Rate limiting ---
    # All limits are configurable from env so deployment can tighten or relax
    # them without code changes.
    RATE_LIMIT_PUBLIC_ENDPOINTS_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_STRICT_IP_PER_MINUTE: int = 10
    RATE_LIMIT_AUTH_MANAGEMENT_IP_PER_MINUTE: int = 30
    RATE_LIMIT_AUTH_USER_ACTIONS_PER_MINUTE: int = 90
    RATE_LIMIT_READ_ACTIONS_PER_MINUTE: int = 120
    RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE: int = 45
    RATE_LIMIT_CHAT_ACTIONS_PER_MINUTE: int = 20
    RATE_LIMIT_UPLOAD_ACTIONS_PER_MINUTE: int = 10
    RATE_LIMIT_AUTH_FAILURE_WINDOW_SECONDS: int = 900
    RATE_LIMIT_AUTH_FAILURE_BACKOFF_BASE_SECONDS: int = 5
    RATE_LIMIT_AUTH_FAILURE_BACKOFF_MAX_SECONDS: int = 900
    RATE_LIMIT_AUTH_FAILURE_BACKOFF_THRESHOLD: int = 2

    # --- JWT ---
    JWT_SECRET_KEY: str = "change-this-to-a-long-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- LLM providers ---
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # --- Embeddings ---
    # Groq has no embeddings API — valid values are "openai" or "gemini".
    EMBEDDING_PROVIDER: str = "openai"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    EMBEDDING_DIMENSIONS: int = 1536

    # --- Vector store ---
    CHROMA_URL: str = ""
    CHROMA_SSL: bool = False
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION: str = "research_documents"

    # --- Uploads ---
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 25

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    def has_provider_key(self, provider: str) -> bool:
        return bool(
            {
                "openai": self.OPENAI_API_KEY,
                "groq": self.GROQ_API_KEY,
                "gemini": self.GEMINI_API_KEY,
            }.get(provider)
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self.SMTP_HOST
            and self.SMTP_USERNAME
            and self.SMTP_PASSWORD
            and self.SMTP_FROM_EMAIL
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — env is only parsed once per process."""
    return Settings()


settings = get_settings()
