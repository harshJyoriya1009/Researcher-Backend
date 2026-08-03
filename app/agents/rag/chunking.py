"""
Splits page text into overlapping chunks suitable for embedding.
Each chunk carries enough metadata to be cited back to a page/section.
"""
from dataclasses import dataclass

from app.agents.rag.parser import PageText

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    approx_words_per_chunk = max(chunk_size // 6, 50)  # ~6 chars/word average
    overlap_words = max(overlap // 6, 10)

    while start < len(words):
        end = min(start + approx_words_per_chunk, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words

    return chunks


def chunk_pages(
    pages: list[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_index = 0

    for page_number, text in pages:
        for piece in _split_text(text, chunk_size, overlap):
            if piece.strip():
                chunks.append(Chunk(text=piece, page_number=page_number, chunk_index=chunk_index))
                chunk_index += 1

    return chunks
