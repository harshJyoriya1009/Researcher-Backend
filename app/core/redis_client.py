"""
Async Redis client singleton — same lazy-singleton pattern already used for
the LLM provider, embedding provider, and vector store
(see app/agents/llm/provider.py, app/agents/rag/embeddings.py,
app/agents/rag/vector_store.py). Kept as a plain module-level singleton for
consistency rather than FastAPI dependency injection.
"""
import redis.asyncio as redis

from app.core.config import settings

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client
