from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.database.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.research_report import ResearchReport
    from app.models.user import User


class ResearchSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "research_sessions"

    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="New research chat", nullable=False)
    model: Mapped[str] = mapped_column(
        String(100), default=lambda: settings.DEFAULT_LLM_MODEL, nullable=False
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    reports: Mapped[list[ResearchReport]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResearchSession id={self.id} title={self.title!r}>"
