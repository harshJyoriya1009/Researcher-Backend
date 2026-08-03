from uuid import UUID

from sqlalchemy import select

from app.models.message import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def list_for_session(self, session_id: UUID, limit: int | None = None) -> list[Message]:
        stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        if limit:
            stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        return list(reversed(messages)) if limit else messages
