from uuid import UUID

import re
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag.chunking import chunk_pages
from app.agents.rag.embeddings import get_embedding_provider
from app.agents.rag.parser import extract_pages
from app.agents.rag.vector_store import get_vector_store
from app.core.config import settings
from app.core.exceptions import DocumentProcessingError, NotFoundError, ValidationFailedError
from app.core.logging import logger
from app.database.session import AsyncSessionLocal
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import PaginatedResponse
from app.schemas.document import DocumentRead
from app.utils.file_storage import delete_upload, resolve_path, save_upload

try:
    import magic as libmagic
except ImportError:  # pragma: no cover - used when libmagic isn't available locally
    libmagic = None

_EXTENSION_TO_TYPE = {
    "pdf": DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "txt": DocumentType.TXT,
}

_UPLOAD_FILENAME_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9 _.,'()-]*[A-Za-z0-9])?\.(pdf|docx|txt)$",
    re.IGNORECASE,
)


def _resolve_document_type(filename: str) -> DocumentType:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    doc_type = _EXTENSION_TO_TYPE.get(ext)
    if doc_type is None:
        raise ValidationFailedError("Only PDF, DOCX, and TXT files are supported.")
    return doc_type


def _validate_filename(filename: str) -> None:
    if len(filename) > 255:
        raise ValidationFailedError("Filename must be 255 characters or fewer.")
    if "/" in filename or "\\" in filename:
        raise ValidationFailedError("Filename must not contain path separators.")
    if not _UPLOAD_FILENAME_PATTERN.match(filename):
        raise ValidationFailedError(
            "Filename must use only letters, numbers, spaces, dots, commas, underscores, "
            "apostrophes, parentheses, or hyphens, and end with .pdf, .docx, or .txt."
        )


_EXPECTED_MIME_TYPES = {
    DocumentType.PDF: {"application/pdf"},
    DocumentType.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    DocumentType.TXT: None,
}


def _sniff_mime_type(sample: bytes) -> str:
    if libmagic is not None:
        try:
            return libmagic.from_buffer(sample, mime=True)
        except Exception:  # noqa: BLE001 - fall back to a light heuristic if libmagic is unavailable
            pass

    if sample.startswith(b"%PDF"):
        return "application/pdf"
    if sample.startswith(b"PK"):
        return "application/zip"
    try:
        sample.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


def _validate_content_matches_extension(doc_type: DocumentType, sample: bytes) -> None:
    detected = _sniff_mime_type(sample)
    expected = _EXPECTED_MIME_TYPES[doc_type]
    if doc_type == DocumentType.TXT:
        if not detected.startswith("text/"):
            raise ValidationFailedError(
                f"File content doesn't look like plain text (detected: {detected})."
            )
    elif detected not in expected:
        raise ValidationFailedError(f"File content doesn't match its extension (detected: {detected}).")


class DocumentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.documents = DocumentRepository(session)

    async def list_documents(self, user: User, page: int, page_size: int) -> PaginatedResponse[DocumentRead]:
        offset = (page - 1) * page_size
        docs, total = await self.documents.list_for_user(user.id, limit=page_size, offset=offset)
        items = [DocumentRead.model_validate(d) for d in docs]
        return PaginatedResponse[DocumentRead](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )

    async def upload_document(self, user: User, file: UploadFile) -> DocumentRead:
        if not file.filename:
            raise ValidationFailedError("A filename is required.")

        _validate_filename(file.filename)
        doc_type = _resolve_document_type(file.filename)

        size_bytes = 0
        chunk = await file.read(1024 * 1024)
        sample = chunk[:2048] if chunk else b""
        while chunk:
            size_bytes += len(chunk)
            if size_bytes > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                raise ValidationFailedError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit.")
            chunk = await file.read(1024 * 1024)
        _validate_content_matches_extension(doc_type, sample)
        await file.seek(0)

        document = await self.documents.create(
            user_id=user.id,
            name=file.filename,
            type=doc_type,
            status=DocumentStatus.UPLOADING,
            size_bytes=size_bytes,
            storage_path="",
        )

        try:
            path = await save_upload(document.id, file)
        except OSError as exc:
            logger.exception("Failed to store uploaded document")
            raise ValidationFailedError("The server could not store this upload.") from exc

        document = await self.documents.update(
            document, status=DocumentStatus.PROCESSING, storage_path=str(path)
        )
        await self.session.commit()

        return DocumentRead.model_validate(document)

    async def delete_document(self, user: User, document_id: UUID) -> None:
        document = await self.documents.get_owned(document_id, user.id)
        if not document:
            raise NotFoundError("Document not found.")

        delete_upload(document.storage_path)
        get_vector_store().delete_document(document.id)
        await self.documents.delete(document)
        await self.session.commit()


async def process_document_task(document_id: UUID) -> None:
    """
    Background job: extract text -> chunk -> embed -> store in ChromaDB.
    Runs in its own DB session since the request session is long gone
    by the time this executes.
    """
    async with AsyncSessionLocal() as session:
        repo = DocumentRepository(session)
        document: Document | None = await repo.get_by_id(document_id)
        if document is None:
            logger.warning(f"process_document_task: document {document_id} not found")
            return

        try:
            pages = extract_pages(resolve_path(document.storage_path), document.type)
            chunks = chunk_pages(pages)
            if not chunks:
                raise DocumentProcessingError("Document produced no indexable text.")

            embedder = get_embedding_provider()
            embeddings = await embedder.embed([c.text for c in chunks])

            get_vector_store().add_chunks(
                document_id=document.id,
                document_name=document.name,
                user_id=document.user_id,
                chunks=[{"text": c.text, "page_number": c.page_number, "chunk_index": c.chunk_index} for c in chunks],
                embeddings=embeddings,
            )

            await repo.update(
                document,
                status=DocumentStatus.READY,
                page_count=len({c.page_number for c in chunks}),
                chunk_count=len(chunks),
            )
            logger.info(f"Document {document_id} processed: {len(chunks)} chunks indexed")

        except Exception as exc:  # noqa: BLE001 — always persist a failure state
            logger.exception(f"Document {document_id} processing failed")
            await repo.update(
                document,
                status=DocumentStatus.ERROR,
                error_message="Document processing failed.",
            )

        await session.commit()
