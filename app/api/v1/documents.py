from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession, user_action_rate_limit
from app.core.config import settings
from app.schemas.common import PaginatedResponse
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService, process_document_task

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: None = Depends(
        user_action_rate_limit(
            scope="documents:upload",
            limit=settings.RATE_LIMIT_UPLOAD_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> DocumentRead:
    document = await DocumentService(db).upload_document(current_user, file)
    background_tasks.add_task(process_document_task, document.id)
    return document


@router.get("", response_model=PaginatedResponse[DocumentRead])
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: None = Depends(
        user_action_rate_limit(
            scope="documents:read",
            limit=settings.RATE_LIMIT_READ_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> PaginatedResponse[DocumentRead]:
    return await DocumentService(db).list_documents(current_user, page=page, page_size=page_size)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    _: None = Depends(
        user_action_rate_limit(
            scope="documents:write",
            limit=settings.RATE_LIMIT_WRITE_ACTIONS_PER_MINUTE,
            window_seconds=60,
        )
    ),
) -> None:
    await DocumentService(db).delete_document(current_user, document_id)
