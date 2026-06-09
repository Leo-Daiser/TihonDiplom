from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.tasks import ensure_task_access
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.task import Task
from app.models.user import User
from app.schemas.attachment import AttachmentDownloadResponse, AttachmentResponse
from app.services.audit_service import write_audit_log
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter(prefix="/api/v1", tags=["attachments"])


@router.get("/tasks/{task_id}/attachments", response_model=list[AttachmentResponse])
def list_task_attachments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Attachment]:
    """Список вложений доступен только пользователям, имеющим доступ к задаче."""
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    ensure_task_access(task, current_user)
    return db.query(Attachment).filter(Attachment.task_id == task_id).order_by(Attachment.created_at.desc()).all()


@router.post("/tasks/{task_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_task_attachment(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageService = Depends(get_storage_service),
) -> Attachment:
    """Файл загружается в MinIO, а в базе сохраняются только сведения о нем."""
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    ensure_task_access(task, current_user)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл не сохраняется")

    object_key = storage.upload_bytes(filename=file.filename or "file", data=data, content_type=file.content_type)
    attachment = Attachment(
        task_id=task_id,
        uploaded_by_id=current_user.id,
        file_name=file.filename or "file",
        object_key=object_key,
        content_type=file.content_type,
        size_bytes=len(data),
    )
    db.add(attachment)
    db.flush()
    write_audit_log(
        db,
        actor_id=current_user.id,
        entity_type="attachment",
        entity_id=attachment.id,
        action="upload_attachment",
        diff={"task_id": task_id, "file_name": attachment.file_name, "size_bytes": attachment.size_bytes},
    )
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/attachments/{attachment_id}/download", response_model=AttachmentDownloadResponse)
def get_attachment_download_url(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageService = Depends(get_storage_service),
) -> AttachmentDownloadResponse:
    """API возвращает временную ссылку на скачивание файла, если нужен прямой доступ к MinIO."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вложение не найдено")
    task = db.get(Task, attachment.task_id)
    ensure_task_access(task, current_user)
    return AttachmentDownloadResponse(url=storage.get_presigned_download_url(attachment.object_key))


@router.get("/attachments/{attachment_id}/open")
def open_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageService = Depends(get_storage_service),
):
    """Файл отдается через приложение: браузеру не нужно иметь прямой доступ к MinIO."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вложение не найдено")
    task = db.get(Task, attachment.task_id)
    ensure_task_access(task, current_user)

    filename = quote(attachment.file_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        "Content-Length": str(attachment.size_bytes),
    }
    return StreamingResponse(
        storage.stream_object(attachment.object_key),
        media_type=attachment.content_type or "application/octet-stream",
        headers=headers,
    )
