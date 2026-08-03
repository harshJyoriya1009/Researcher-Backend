from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.message import Message
from app.models.research_session import ResearchSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[ResearchSession]):
    model = ResearchSession

    async def list_for_user(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[tuple[ResearchSession, int]], int]:
        count_stmt = select(func.count(ResearchSession.id)).where(ResearchSession.user_id == user_id)
        total = int(await self.session.scalar(count_stmt) or 0)

        stmt = (
            select(ResearchSession, func.count(Message.id).label("message_count"))
            .outerjoin(Message, Message.session_id == ResearchSession.id)
            .where(ResearchSession.user_id == user_id)
            .group_by(ResearchSession.id)
            .order_by(ResearchSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()], total

    async def get_with_messages(self, session_id: UUID, user_id: UUID) -> ResearchSession | None:
        stmt = (
            select(ResearchSession)
            .options(selectinload(ResearchSession.messages))
            .where(ResearchSession.id == session_id, ResearchSession.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned(self, session_id: UUID, user_id: UUID) -> ResearchSession | None:
        stmt = select(ResearchSession).where(
            ResearchSession.id == session_id, ResearchSession.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
