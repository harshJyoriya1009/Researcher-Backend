"""
Generator node: builds the prompt (with retrieved context if any) and
calls the selected LLM to produce the final answer.
"""
from app.agents.graph.state import ResearchState
from app.agents.llm.provider import get_llm_provider
from app.core.config import settings
from app.core.logging import logger

SYSTEM_PROMPT = (
    f"You are {settings.APP_NAME}, an AI research assistant. Answer clearly and concisely. "
    f"If asked your name or identity, say exactly: \"I'm {settings.APP_NAME}, your AI research assistant.\" "
    "Do not say ChatGPT or OpenAI. "
    "When source context is provided, ground your answer in it and reference sources "
    "using [1], [2], etc. matching the order they were given. Retrieved context may "
    "come from multiple different documents, grouped and labeled above. Do not mix or "
    "combine facts from different documents unless the user's question explicitly asks "
    "you to compare them. If a fact appears in one document but the user's question "
    "seems to be about a different one, say so. If the context doesn't answer the "
    "question, say so honestly rather than guessing."
)


def build_messages(state: ResearchState) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    chunks = state.get("retrieved_chunks") or []
    if chunks:
        grouped_chunks: dict[str, list[tuple[int, dict]]] = {}
        for index, chunk in enumerate(chunks, start=1):
            grouped_chunks.setdefault(chunk["document_name"], []).append((index, chunk))

        context_sections = []
        for document_name, document_chunks in grouped_chunks.items():
            chunk_lines = "\n\n".join(
                f"[{index}] (page {chunk['page_number']}):\n{chunk['text']}"
                for index, chunk in document_chunks
            )
            context_sections.append(f'--- From "{document_name}" ---\n{chunk_lines}')

        context_block = "\n\n".join(context_sections)
        messages.append(
            {
                "role": "system",
                "content": f"Relevant context retrieved from the user's documents:\n\n{context_block}",
            }
        )

    messages.extend(state.get("conversation_history", []))
    messages.append({"role": "user", "content": state["query"]})
    return messages


def build_citations(state: ResearchState) -> list[dict]:
    chunks = state.get("retrieved_chunks") or []
    return [
        {
            "id": c["id"],
            "title": f"{c['document_name']} (p. {c['page_number']})",
            "url": f"document://{c['document_id']}#chunk-{c['chunk_index']}",
            "snippet": c["text"][:200],
        }
        for c in chunks
    ]


async def generator_node(state: ResearchState) -> dict:
    llm = get_llm_provider()
    model = state.get("model") or settings.DEFAULT_LLM_MODEL
    messages = build_messages(state)

    result = await llm.complete(messages=messages, model_id=model)

    logger.debug(f"Generated answer ({result.usage.total_tokens} tokens, model={model})")

    return {
        "answer": result.content,
        "citations": build_citations(state),
        "provider": result.provider,
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "total_tokens": result.usage.total_tokens,
    }
