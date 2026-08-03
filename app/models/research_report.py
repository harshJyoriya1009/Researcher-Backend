from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_session import ResearchSession


class ResearchReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Evaluation metrics captured for a single generated response."""

    __tablename__ = "research_reports"

    session_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    used_retrieval: Mapped[bool] = mapped_column(default=False, nullable=False)
    retrieved_chunk_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    guardrail_passed: Mapped[bool] = mapped_column(default=True, nullable=False)

    session: Mapped[ResearchSession] = relationship(back_populates="reports")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResearchReport id={self.id} session_id={self.session_id}>"
