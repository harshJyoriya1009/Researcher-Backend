"""
Thin abstraction over LiteLLM so the rest of the codebase never imports
`litellm` directly. Swapping providers (OpenAI / Groq / Gemini) is just
a matter of changing the `model` string LiteLLM receives.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.core.logging import logger

# LiteLLM model prefixes per provider, e.g. "groq/openai/gpt-oss-20b"
PROVIDER_PREFIXES = {
    "openai": "",  # OpenAI models need no prefix in LiteLLM
    "groq": "groq/",
    "gemini": "gemini/",
}

AVAILABLE_MODELS = [
    {
        "id": "gpt-4o-mini",
        "label": "Research Fast (GPT-4o mini)",
        "provider": "openai",
        "description": "Low latency, good for quick lookups and drafts.",
    },
    {
        "id": "gpt-4o",
        "label": "Research Large (GPT-4o)",
        "provider": "openai",
        "description": "Deepest analysis, best for literature reviews and synthesis.",
    },
    {
        "id": "openai/gpt-oss-20b",
        "label": "Research Reasoning (GPT-OSS 20B via Groq)",
        "provider": "groq",
        "description": "Fast open-weight reasoning model hosted on Groq.",
    },
    {
        "id": "gemini-3.5-flash",
        "label": "Research Gemini (3.5 Flash)",
        "provider": "gemini",
        "description": "Google's current-generation model, tuned for agentic and coding tasks.",
    },
]

_MODEL_TO_PROVIDER = {m["id"]: m["provider"] for m in AVAILABLE_MODELS}


def get_available_models() -> list[dict]:
    """AVAILABLE_MODELS annotated with whether each provider's API key is set."""
    return [{**m, "configured": settings.has_provider_key(m["provider"])} for m in AVAILABLE_MODELS]


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResult:
    content: str
    usage: LLMUsage
    model: str
    provider: str


def resolve_litellm_model(model_id: str) -> tuple[str, str]:
    """Return (litellm_model_string, provider_name) for a given model id."""
    provider = _MODEL_TO_PROVIDER.get(model_id, settings.DEFAULT_LLM_PROVIDER)
    prefix = PROVIDER_PREFIXES.get(provider, "")
    return f"{prefix}{model_id}", provider


class LLMProvider:
    """Chat-completion + streaming interface backed by LiteLLM."""

    def __init__(self) -> None:
        import litellm

        litellm.drop_params = True
        litellm.set_verbose = False
        self._litellm = litellm

    def _api_key_for(self, provider: str) -> str | None:
        return {
            "openai": settings.OPENAI_API_KEY,
            "groq": settings.GROQ_API_KEY,
            "gemini": settings.GEMINI_API_KEY,
        }.get(provider)

    async def complete(
        self,
        messages: list[dict[str, str]],
        model_id: str,
        temperature: float = 0.3,
    ) -> LLMResult:
        litellm_model, provider = resolve_litellm_model(model_id)
        try:
            response = await self._litellm.acompletion(
                model=litellm_model,
                messages=messages,
                temperature=temperature,
                api_key=self._api_key_for(provider),
            )
        except Exception as exc:  # noqa: BLE001 — provider errors vary widely
            logger.exception(f"LLM completion failed (model={model_id})")
            raise LLMProviderError("The language model request failed.") from exc

        choice = response.choices[0].message.content or ""
        usage = response.get("usage") or {}
        return LLMResult(
            content=choice,
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            model=model_id,
            provider=provider,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        model_id: str,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        litellm_model, provider = resolve_litellm_model(model_id)
        try:
            response = await self._litellm.acompletion(
                model=litellm_model,
                messages=messages,
                temperature=temperature,
                api_key=self._api_key_for(provider),
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"LLM streaming failed (model={model_id})")
            raise LLMProviderError("The language model request failed.") from exc


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider
