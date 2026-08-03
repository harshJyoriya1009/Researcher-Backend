from app.models.document import DocumentStatus, DocumentType
from app.schemas.common import TimestampedSchema


class DocumentRead(TimestampedSchema):
    name: str
    type: DocumentType
    status: DocumentStatus
    size_bytes: int
    page_count: int | None = None
    chunk_count: int | None = None
    error_message: str | None = None
