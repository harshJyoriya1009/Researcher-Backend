import asyncio
import json
import time
import re
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph.nodes.evaluator import evaluator_node
from app.agents.graph.nodes.generator import build_citations, build_messages
from app.agents.graph.nodes.guardrail import guardrail_node
from app.agents.graph.nodes.planner import planner_node
from app.agents.graph.nodes.retriever import retriever_node
from app.agents.graph.state import ResearchState
from app.agents.llm.provider import get_llm_provider, resolve_litellm_model
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import logger
from app.database.session import AsyncSessionLocal
from app.models.message import MessageRole
from app.models.research_session import ResearchSession
from app.models.user import User
from app.repositories.message_repository import MessageRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import PaginatedResponse
from app.schemas.research import MessageRead, SessionDetail, SessionRead

HISTORY_WINDOW = 10  # most recent messages fed back to the LLM as context

GUARDRAIL_FALLBACK_MESSAGE = (
    "I wasn't able to produce a response that passed safety checks for that request. "
    "Could you rephrase it?"
)

IDENTITY_QUESTION_PATTERNS = (
    re.compile(r"\bwhat(?:'s| is)? your name\b", re.IGNORECASE),
    re.compile(r"\bwho are you\b", re.IGNORECASE),
    re.compile(r"\bwhat do i call you\b", re.IGNORECASE),
    re.compile(r"\bwhat should i call you\b", re.IGNORECASE),
    re.compile(r"\bintroduce yourself\b", re.IGNORECASE),
    re.compile(r"\bare you chatgpt\b", re.IGNORECASE),
)


def _session_to_read(session: ResearchSession, message_count: int) -> SessionRead:
    return SessionRead(
        id=session.id,
        title=session.title,
        model=session.model,
        pinned=session.pinned,
        message_count=message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


class ResearchService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.sessions = SessionRepository(db_session)
        self.messages = MessageRepository(db_session)
        self.reports = ReportRepository(db_session)

    def _is_identity_question(self, content: str) -> bool:
        normalized = content.strip().lower()
        return any(pattern.search(normalized) for pattern in IDENTITY_QUESTION_PATTERNS)

    # ---------------------------------------------------------------- CRUD

    async def list_sessions(self, user: User, page: int, page_size: int) -> PaginatedResponse[SessionRead]:
        offset = (page - 1) * page_size
        rows, total = await self.sessions.list_for_user(user.id, limit=page_size, offset=offset)
        items = [_session_to_read(session, count) for session, count in rows]
        return PaginatedResponse[SessionRead](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )

    async def create_session(self, user: User, title: str | None, model: str | None) -> SessionRead:
        session = await self.sessions.create(
            user_id=user.id,
            title=title or "New research chat",
            model=model or user.default_model,
        )
        await self.db.commit()
        return _session_to_read(session, 0)

    async def get_session_detail(self, user: User, session_id: UUID) -> SessionDetail:
        session = await self.sessions.get_with_messages(session_id, user.id)
        if not session:
            raise NotFoundError("Research session not found.")
        return SessionDetail(
            session=_session_to_read(session, len(session.messages)),
            messages=[MessageRead.model_validate(m) for m in session.messages],
        )

    async def rename_session(self, user: User, session_id: UUID, title: str) -> SessionRead:
        session = await self.sessions.get_owned(session_id, user.id)
        if not session:
            raise NotFoundError("Research session not found.")
        session = await self.sessions.update(session, title=title)
        await self.db.commit()
        count = len(await self.messages.list_for_session(session_id))
        return _session_to_read(session, count)

    async def delete_session(self, user: User, session_id: UUID) -> None:
        session = await self.sessions.get_owned(session_id, user.id)
        if not session:
            raise NotFoundError("Research session not found.")
        await self.sessions.delete(session)
        await self.db.commit()

    # ---------------------------------------------------------------- Chat

    async def stream_chat(
        self,
        user: User,
        session_id: UUID | None,
        content: str,
        model: str | None,
        document_ids: list[UUID] | None,
    ) -> AsyncIterator[str]:
        """
        Runs the planner -> retriever -> (streamed generation) -> guardrail ->
        evaluator pipeline, yielding SSE-formatted `data: {...}\\n\\n` lines as
        tokens are produced. The DB session, message, and evaluation report
        are persisted once the stream completes.
        """
        session = await self._get_or_create_session(user, session_id, model)
        resolved_model = model or session.model

        history = await self._recent_history(session.id)
        await self.messages.create(session_id=session.id, role=MessageRole.USER, content=content)
        await self.db.commit()

        state: ResearchState = {
            "user_id": user.id,
            "session_id": session.id,
            "query": content,
            "conversation_history": history,
            "document_ids": document_ids,
            "model": resolved_model,
        }

        if self._is_identity_question(content):
            answer = f"I'm {settings.APP_NAME}, your AI research assistant."
            yield f"data: {json.dumps({'token': answer})}\n\n"
            yield f"data: {json.dumps({'citations': [], 'session_id': str(session.id)})}\n\n"
            yield "data: [DONE]\n\n"

            asyncio.create_task(
                _persist_assistant_turn(
                    session_id=session.id,
                    original_title=session.title,
                    first_user_message=content,
                    provider="local",
                    model=resolved_model,
                    final_answer=answer,
                    final_citations=[],
                    faithfulness=None,
                    relevance=None,
                    latency_ms=0,
                    used_retrieval=False,
                    retrieved_chunk_ids=None,
                    guardrail_passed=True,
                )
            )
            return

        start = time.perf_counter()

        state.update(await planner_node(state))
        state.update(await retriever_node(state))

        llm = get_llm_provider()
        messages_for_llm = build_messages(state)
        litellm_model, provider = resolve_litellm_model(resolved_model)

        accumulated = ""
        try:
            async for token in llm.stream(messages_for_llm, resolved_model):
                accumulated += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Streaming generation failed")
            if not accumulated:
                accumulated = "Sorry, I couldn't generate a response just now. Please try again."
                yield f"data: {json.dumps({'token': accumulated})}\n\n"

        state["answer"] = accumulated
        state["citations"] = build_citations(state)
        state["provider"] = provider

        state.update(await guardrail_node(state))
        state.update(await evaluator_node(state))

        latency_ms = int((time.perf_counter() - start) * 1000)

        final_answer = state["answer"]
        final_citations = state["citations"]
        if not state.get("guardrail_passed", True):
            final_answer = GUARDRAIL_FALLBACK_MESSAGE
            final_citations = []
            yield f"data: {json.dumps({'token': '', 'guardrail_blocked': True})}\n\n"

        yield f"data: {json.dumps({'citations': final_citations, 'session_id': str(session.id)})}\n\n"
        yield "data: [DONE]\n\n"

        asyncio.create_task(
            _persist_assistant_turn(
                session_id=session.id,
                original_title=session.title,
                first_user_message=content,
                provider=provider,
                model=resolved_model,
                final_answer=final_answer,
                final_citations=final_citations,
                faithfulness=state.get("faithfulness"),
                relevance=state.get("relevance"),
                latency_ms=latency_ms,
                used_retrieval=bool(state.get("needs_retrieval")),
                retrieved_chunk_ids=[c["id"] for c in state.get("retrieved_chunks", [])] or None,
                guardrail_passed=state.get("guardrail_passed", True),
            )
        )

    async def _get_or_create_session(
        self, user: User, session_id: UUID | None, model: str | None
    ) -> ResearchSession:
        if session_id:
            session = await self.sessions.get_owned(session_id, user.id)
            if not session:
                raise NotFoundError("Research session not found.")
            return session

        return await self.sessions.create(
            user_id=user.id, title="New research chat", model=model or user.default_model
        )

    async def _recent_history(self, session_id: UUID) -> list[dict[str, str]]:
        recent = await self.messages.list_for_session(session_id, limit=HISTORY_WINDOW)
        return [{"role": m.role.value, "content": m.content} for m in recent]

    @staticmethod
    def _derive_title(current_title: str, first_message: str) -> str:
        if current_title != "New research chat":
            return current_title
        trimmed = first_message.strip().replace("\n", " ")
        return trimmed[:60] + ("…" if len(trimmed) > 60 else "")


async def _persist_assistant_turn(
    session_id: UUID,
    original_title: str,
    first_user_message: str,
    provider: str,
    model: str,
    final_answer: str,
    final_citations: list[dict],
    faithfulness: float | None,
    relevance: float | None,
    latency_ms: int,
    used_retrieval: bool,
    retrieved_chunk_ids: list[str] | None,
    guardrail_passed: bool,
) -> None:
    """
    Persists the assistant's message, its evaluation report, and the session
    title update in the background, using a fresh DB session.

    Trade-off: if the process crashes between the SSE stream finishing and this
    task completing, the assistant's message/report could be lost even though
    the user already saw it. Acceptable for this app; revisit if durability
    matters more than perceived latency.
    """
    async with AsyncSessionLocal() as session:
        try:
            messages_repo = MessageRepository(session)
            reports_repo = ReportRepository(session)
            sessions_repo = SessionRepository(session)

            assistant_message = await messages_repo.create(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=final_answer,
                citations=final_citations or None,
            )

            await reports_repo.create(
                session_id=session_id,
                message_id=assistant_message.id,
                provider=provider,
                model=model,
                faithfulness=faithfulness,
                relevance=relevance,
                latency_ms=latency_ms,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                used_retrieval=used_retrieval,
                retrieved_chunk_ids=retrieved_chunk_ids,
                guardrail_passed=guardrail_passed,
            )

            db_session = await sessions_repo.get_by_id(session_id)
            if db_session:
                db_session.title = ResearchService._derive_title(
                    original_title, first_user_message
                )

            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to persist assistant turn for session {session_id}")
