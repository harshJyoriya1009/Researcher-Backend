"""
Retriever node: embeds the query and searches ChromaDB for relevant
document chunks scoped to the current user (and optionally a specific
set of documents).
"""
from app.agents.graph.state import ResearchState
from app.agents.rag.embeddings import get_embedding_provider
from app.agents.rag.vector_store import get_vector_store
from app.core.logging import logger

MIN_RELEVANCE_SCORE = 0.25
TOP_K = 3


async def retriever_node(state: ResearchState) -> dict:
    if not state.get("needs_retrieval"):
        return {"retrieved_chunks": []}

    try:
        embeddings = get_embedding_provider()
        store = get_vector_store()
        query_embedding = await embeddings.embed_one(state["query"])
        results = store.query(
            query_embedding=query_embedding,
            user_id=state["user_id"],
            document_ids=state.get("document_ids"),
            top_k=TOP_K,
        )
    except Exception as exc:  # noqa: BLE001 — retrieval failure shouldn't crash the chat
        logger.warning(f"Retrieval failed, falling back to no-context answer: {exc}")
        return {"retrieved_chunks": []}

    relevant = [r for r in results if r.score >= MIN_RELEVANCE_SCORE]
    logger.debug(f"Retrieved {len(relevant)}/{len(results)} chunks above relevance threshold")

    return {
        "retrieved_chunks": [
            {
                "id": r.id,
                "text": r.text,
                "document_id": r.document_id,
                "document_name": r.document_name,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "score": r.score,
            }
            for r in relevant
        ]
    }
