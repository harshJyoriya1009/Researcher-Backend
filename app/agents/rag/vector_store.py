"""
Wraps ChromaDB so the rest of the app talks to a small, typed interface
instead of the raw client. Each stored chunk carries document_id,
page_number, chunk_index, and free-form metadata as required by the
RAG pipeline spec.
"""
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.core.config import settings
from app.core.logging import logger


@dataclass
class RetrievedChunk:
    id: str
    text: str
    document_id: str
    document_name: str
    page_number: int
    chunk_index: int
    score: float


class VectorStore:
    def __init__(self) -> None:
        import chromadb

        self._client = self._create_client(chromadb)
        self._collection = self._client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def _create_client(self, chromadb_module: Any) -> Any:
        if settings.CHROMA_URL:
            parsed = urlparse(settings.CHROMA_URL)
            if not parsed.hostname:
                raise ValueError("CHROMA_URL must include a hostname")

            scheme = parsed.scheme.lower()
            ssl = settings.CHROMA_SSL or scheme == "https"
            port = parsed.port or (443 if ssl else 8000)

            return chromadb_module.HttpClient(host=parsed.hostname, port=port, ssl=ssl)

        return chromadb_module.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            ssl=settings.CHROMA_SSL,
        )

    def add_chunks(
        self,
        document_id: UUID,
        document_name: str,
        user_id: UUID,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        ids = [f"{document_id}_{c['chunk_index']}" for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "document_id": str(document_id),
                "document_name": document_name,
                "user_id": str(user_id),
                "page_number": c["page_number"],
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ]
        self._collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        logger.info(f"Indexed {len(chunks)} chunks for document {document_id}")

    def query(
        self,
        query_embedding: list[float],
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        where: dict[str, Any] = {"user_id": str(user_id)}
        if document_ids:
            where = {
                "$and": [
                    {"user_id": str(user_id)},
                    {"document_id": {"$in": [str(d) for d in document_ids]}},
                ]
            }

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )

        chunks: list[RetrievedChunk] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] or {}
            chunks.append(
                RetrievedChunk(
                    id=chunk_id,
                    text=docs[i],
                    document_id=meta.get("document_id", ""),
                    document_name=meta.get("document_name", ""),
                    page_number=meta.get("page_number", 0),
                    chunk_index=meta.get("chunk_index", 0),
                    score=1 - distances[i] if i < len(distances) else 0.0,
                )
            )
        return chunks

    def delete_document(self, document_id: UUID) -> None:
        self._collection.delete(where={"document_id": str(document_id)})


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
