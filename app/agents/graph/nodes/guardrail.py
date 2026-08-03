"""
Guardrail node: lightweight, dependency-free safety checks that run
after generation. These are heuristic by design — fast, deterministic,
and good enough to catch the common failure modes (empty output,
obvious prompt-injection artifacts leaking into the answer, a handful
of flagged terms, and answers that ignore retrieved context entirely).

For higher-fidelity moderation, swap `_toxicity_check` for a call to a
moderation API/model without changing the node's contract.
"""
import re

from app.agents.graph.state import ResearchState
from app.core.logging import logger

_INJECTION_PATTERNS = (
    re.compile(r"ignore (all|any|previous) instructions", re.IGNORECASE),
    re.compile(r"disregard (the|your) system prompt", re.IGNORECASE),
    re.compile(r"you are now (in )?(dan|developer) mode", re.IGNORECASE),
    re.compile(r"reveal your (system prompt|instructions)", re.IGNORECASE),
)

_TOXIC_TERMS = frozenset(
    {
        # Intentionally minimal — a real deployment should call a
        # dedicated moderation model rather than a static keyword list.
        "kill yourself",
        "hate speech",
    }
)


def _prompt_injection_detected(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def _toxicity_detected(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _TOXIC_TERMS)


def _is_grounded(state: ResearchState) -> bool:
    """If retrieval ran, require at least loose lexical overlap with the answer."""
    chunks = state.get("retrieved_chunks") or []
    if not chunks:
        return True  # nothing to ground against — direct-answer path is fine

    answer_words = set(re.findall(r"\w+", state.get("answer", "").lower()))
    context_words: set[str] = set()
    for chunk in chunks:
        context_words.update(re.findall(r"\w+", chunk["text"].lower()))

    overlap = answer_words & context_words
    return len(overlap) >= 3


async def guardrail_node(state: ResearchState) -> dict:
    answer = state.get("answer", "").strip()

    if not answer:
        logger.warning("Guardrail: empty response")
        return {"guardrail_passed": False, "guardrail_reason": "The model returned an empty response."}

    if _prompt_injection_detected(state.get("query", "")) or _prompt_injection_detected(answer):
        logger.warning("Guardrail: possible prompt injection detected")
        return {
            "guardrail_passed": False,
            "guardrail_reason": "The request or response matched a prompt-injection pattern.",
        }

    if _toxicity_detected(answer):
        logger.warning("Guardrail: toxic content detected")
        return {"guardrail_passed": False, "guardrail_reason": "The response failed a safety check."}

    if not _is_grounded(state):
        logger.warning("Guardrail: response not grounded in retrieved context")
        return {
            "guardrail_passed": False,
            "guardrail_reason": "The response didn't appear grounded in the retrieved documents.",
        }

    return {"guardrail_passed": True, "guardrail_reason": None}
