"""
Planner node: decides whether the query requires document retrieval.

Heuristic-first, cheap and deterministic: if the user explicitly
scoped the request to documents, or the session has documents
attached, retrieval is required. This avoids an extra LLM round-trip
on every single message while still being overridable with an
LLM-based classifier later if needed.
"""
from app.agents.graph.state import ResearchState
from app.core.logging import logger

RETRIEVAL_HINT_KEYWORDS = (
    "document",
    "pdf",
    "file",
    "uploaded",
    "attached",
    "according to",
    "in the paper",
    "in the report",
)


async def planner_node(state: ResearchState) -> dict:
    document_ids = state.get("document_ids")
    query = state.get("query", "").lower()

    needs_retrieval = bool(document_ids) or any(kw in query for kw in RETRIEVAL_HINT_KEYWORDS)

    logger.debug(f"Planner decided needs_retrieval={needs_retrieval}")
    return {"needs_retrieval": needs_retrieval}
