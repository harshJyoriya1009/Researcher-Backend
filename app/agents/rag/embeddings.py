"""
Embeddings provider, abstracted the same way as chat completions.

Only OpenAI and Gemini are valid choices for `EMBEDDING_PROVIDER` — Groq
doesn't offer an embeddings endpoint (it's an inference-speed provider for
chat/completion models only). Chat can still use Groq independently; this
module only concerns itself with the embedding call.
"""
from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.core.logging import logger

_EMBEDDING_MODELS = {
    "openai": lambda: settings.OPENAI_EMBEDDING_MODEL,
    "gemini": lambda: f"gemini/{settings.GEMINI_EMBEDDING_MODEL}",
}

_EMBEDDING_API_KEYS = {
    "openai": lambda: settings.OPENAI_API_KEY,
    "gemini": lambda: settings.GEMINI_API_KEY,
}


class EmbeddingProvider:
    def __init__(self) -> None:
        import litellm

        self._litellm = litellm

        provider = settings.EMBEDDING_PROVIDER
        if provider not in _EMBEDDING_MODELS:
            raise LLMProviderError(
                "The selected embedding provider is not supported."
            )
        if not settings.has_provider_key(provider):
            raise LLMProviderError(
                "The selected embedding provider is not configured."
            )

        self._model = _EMBEDDING_MODELS[provider]()
        self._api_key = _EMBEDDING_API_KEYS[provider]()
        self._provider = provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._litellm.aembedding(
                model=self._model,
                input=texts,
                api_key=self._api_key,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Embedding request failed (provider={self._provider})")
            raise LLMProviderError("The embedding request failed.") from exc

        return [item["embedding"] for item in response["data"]]

    async def embed_one(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0] if result else []


_embedding_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = EmbeddingProvider()
    return _embedding_provider
