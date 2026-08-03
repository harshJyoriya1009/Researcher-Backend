"""
TypedDict describing the state threaded through every node of the
research workflow graph (see agents/graph/workflow.py).
"""
from typing import Any, TypedDict
from uuid import UUID


class Citation(TypedDict):
    id: str
    title: str
    url: str
    snippet: str


class ResearchState(TypedDict, total=False):
    # --- Input ---
    user_id: UUID
    session_id: UUID
    query: str
    conversation_history: list[dict[str, str]]
    document_ids: list[UUID] | None
    model: str

    # --- Planner output ---
    needs_retrieval: bool

    # --- Retriever output ---
    retrieved_chunks: list[dict[str, Any]]

    # --- Generator output ---
    answer: str
    citations: list[Citation]
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # --- Guardrail output ---
    guardrail_passed: bool
    guardrail_reason: str | None

    # --- Evaluator output ---
    faithfulness: float
    relevance: float
    latency_ms: int
