from uuid import UUID

from sqlalchemy import func, select

from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def list_for_user(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Document], int]:
        count_stmt = select(func.count(Document.id)).where(Document.user_id == user_id)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_owned(self, document_id: UUID, user_id: UUID) -> Document | None:
        stmt = select(Document).where(Document.id == document_id, Document.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ready_for_user(self, user_id: UUID, document_ids: list[UUID] | None = None) -> list[Document]:
        stmt = select(Document).where(Document.user_id == user_id, Document.status == "ready")
        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
