from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, user_action_rate_limit
from app.core.config import settings
from app.schemas.common import PaginatedResponse
from app.schemas.research import (
    ChatRequest,
    SessionCreateRequest,
    SessionDetail,
    SessionRead,
    SessionRenameRequest,
)
from app.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["Research"])


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="research:chat",
            limit=settings.RATE_LIMIT_CHAT_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> StreamingResponse:
    """
    Streams the assistant's reply as Server-Sent Events. Each event is a
    JSON payload: `{"token": "..."}` while generating, then a final
    `{"citations": [...], "session_id": "..."}` event, then `[DONE]`.
    """
    service = ResearchService(db)
    generator = service.stream_chat(
        user=current_user,
        session_id=payload.session_id,
        content=payload.content,
        model=payload.model,
        document_ids=payload.document_ids,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/history", response_model=PaginatedResponse[SessionRead])
async def history(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: None = Depends(
        user_action_rate_limit(
            scope="research:read",
            limit=settings.RATE_LIMIT_READ_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> PaginatedResponse[SessionRead]:
    return await ResearchService(db).list_sessions(current_user, page=page, page_size=page_size)


@router.post("/session", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="research:write",
            limit=settings.RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> SessionRead:
    return await ResearchService(db).create_session(current_user, payload.title, payload.model)


@router.get("/session/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="research:read",
            limit=settings.RATE_LIMIT_READ_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> SessionDetail:
    return await ResearchService(db).get_session_detail(current_user, session_id)


@router.patch("/session/{session_id}", response_model=SessionRead)
async def rename_session(
    session_id: UUID,
    payload: SessionRenameRequest,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="research:write",
            limit=settings.RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> SessionRead:
    return await ResearchService(db).rename_session(current_user, session_id, payload.title)


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="research:write",
            limit=settings.RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await ResearchService(db).delete_session(current_user, session_id)
