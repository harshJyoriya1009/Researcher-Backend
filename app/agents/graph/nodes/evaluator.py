"""
Evaluator node: lightweight, heuristic quality metrics computed for
every generated response. Latency and token usage are captured by the
generator node / calling service (they're facts about the call, not
judgments about the answer) — this node focuses on faithfulness and
relevance, both approximated via lexical overlap since that requires
no extra model call and is cheap enough to run on every response.
"""
import re

from app.agents.graph.state import ResearchState

_STOPWORDS = frozenset(
    "a an the is are was were be been being of to in on for with and or "
    "this that these those it its as at by from your you i we".split()
)


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _faithfulness(state: ResearchState) -> float:
    """How much of the answer's vocabulary is traceable to retrieved context."""
    chunks = state.get("retrieved_chunks") or []
    if not chunks:
        return 1.0  # no context to be unfaithful to

    answer_tokens = _tokenize(state.get("answer", ""))
    if not answer_tokens:
        return 0.0

    context_tokens: set[str] = set()
    for chunk in chunks:
        context_tokens.update(_tokenize(chunk["text"]))

    overlap = answer_tokens & context_tokens
    return round(min(len(overlap) / max(len(answer_tokens), 1) * 1.5, 1.0), 3)


def _relevance(state: ResearchState) -> float:
    """How much the answer's vocabulary overlaps with the question's."""
    query_tokens = _tokenize(state.get("query", ""))
    answer_tokens = _tokenize(state.get("answer", ""))
    if not query_tokens or not answer_tokens:
        return 0.5

    overlap = query_tokens & answer_tokens
    return round(min(len(overlap) / max(len(query_tokens), 1) * 1.2 + 0.3, 1.0), 3)


async def evaluator_node(state: ResearchState) -> dict:
    return {
        "faithfulness": _faithfulness(state),
        "relevance": _relevance(state),
    }
