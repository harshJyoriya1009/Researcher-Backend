"""
Minimal local-disk storage for uploaded files, keyed by document id.
Swap this module for an S3/GCS-backed implementation in production —
callers only depend on `save_upload` / `delete_upload` / `resolve_path`.
"""
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.config import settings

UPLOAD_ROOT = Path(settings.UPLOAD_DIR).resolve()


def _safe_storage_path(storage_path: str) -> Path:
    path = Path(storage_path).resolve()
    try:
        path.relative_to(UPLOAD_ROOT)
    except ValueError as exc:
        raise ValueError("Invalid upload path.") from exc
    return path


def _ensure_upload_root() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        UPLOAD_ROOT.chmod(0o700)
    except OSError:
        # Permissions are best-effort; Windows and some filesystems may ignore this.
        pass


async def save_upload(document_id: UUID, upload: UploadFile) -> Path:
    _ensure_upload_root()
    suffix = Path(upload.filename or "").suffix
    destination = UPLOAD_ROOT / f"{document_id}{suffix}"

    with destination.open("wb") as buffer:
        while chunk := await upload.read(1024 * 1024):
            buffer.write(chunk)

    try:
        destination.chmod(0o600)
    except OSError:
        # Best-effort hardening; not all platforms support POSIX permissions.
        pass

    await upload.seek(0)
    return destination


def resolve_path(storage_path: str) -> Path:
    return _safe_storage_path(storage_path)


def delete_upload(storage_path: str) -> None:
    path = _safe_storage_path(storage_path)
    if path.exists():
        path.unlink()
