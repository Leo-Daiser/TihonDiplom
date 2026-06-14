from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.services import task_service
from app.services.audit_service import write_audit_log
from app.services.storage_service import StorageService, get_storage_service
from app.web.deps import get_user_from_cookie, redirect_to_login

router = APIRouter(tags=["web-tasks"])
templates = Jinja2Templates(directory="app/templates")


def parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_optional_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def form_context(request: Request, user: User, db: Session, **extra):
    context = {
        "request": request,
        "user": user,
        "statuses": db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all(),
        "priorities": db.query(TaskPriority).order_by(TaskPriority.sort_order.asc()).all(),
        "users": db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name.asc()).all(),
    }
    context.update(extra)
    return context


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, q: str | None = None, status_code: str | None = None, priority_code: str | None = None, assignee_id: str | None = None, source_type: str | None = None, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    assignee_filter = parse_optional_int(assignee_id)
    tasks = task_service.list_tasks_for_user(
        db,
        user,
        q=q,
        status_code=status_code,
        priority_code=priority_code,
        assignee_id=assignee_filter,
        source_type=source_type,
    )
    context = form_context(request, user, db, tasks=tasks, filters={"q": q, "status_code": status_code, "priority_code": priority_code, "assignee_id": assignee_filter, "source_type": source_type}, can_manage=task_service.user_can_manage_tasks(user))
    return templates.TemplateResponse(request, "tasks.html", context)


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task_service.require_task_manager(user)
    context = form_context(request, user, db, task=None, page_title="Новая задача", form_action="/tasks/new", submit_label="Создать задачу")
    return templates.TemplateResponse(request, "task_form.html", context)


@router.post("/tasks/new")
def create_task_from_form(request: Request, title: str = Form(...), description: str | None = Form(default=None), assignee_id: str | None = Form(default=None), priority_code: str = Form("medium"), status_code: str = Form("new"), deadline: str | None = Form(default=None), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task_service.require_task_manager(user)
    task = task_service.create_task_record(
        db,
        actor=user,
        title=title,
        description=description,
        assignee_id=parse_optional_int(assignee_id),
        status_code=status_code,
        priority_code=priority_code,
        deadline=parse_deadline(deadline),
    )
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail_page(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = task_service.get_task_for_user(db, task_id, user, include_attachments=True)
    statuses = db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all()
    context = {"request": request, "user": user, "task": task, "statuses": statuses, "can_manage": task_service.user_can_manage_tasks(user)}
    return templates.TemplateResponse(request, "task_detail.html", context)


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_page(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task_service.require_task_manager(user)
    task = task_service.get_task_or_404(db, task_id)
    context = form_context(request, user, db, task=task, page_title=f"Редактирование задачи #{task.id}", form_action=f"/tasks/{task.id}/edit", submit_label="Сохранить изменения")
    return templates.TemplateResponse(request, "task_form.html", context)


@router.post("/tasks/{task_id}/edit")
def edit_task_submit(request: Request, task_id: int, title: str = Form(...), description: str | None = Form(default=None), assignee_id: str | None = Form(default=None), priority_code: str = Form(...), status_code: str = Form(...), deadline: str | None = Form(default=None), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task_service.require_task_manager(user)
    task = task_service.get_task_or_404(db, task_id)
    updated_task = task_service.update_task_record(
        db,
        task=task,
        actor=user,
        data={
            "title": title,
            "description": description,
            "assignee_id": parse_optional_int(assignee_id),
            "status_code": status_code,
            "priority_code": priority_code,
            "deadline": parse_deadline(deadline),
        },
    )
    return RedirectResponse(url=f"/tasks/{updated_task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/status")
def task_status_submit(request: Request, task_id: int, status_code: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = task_service.change_task_status_for_user(db, task_id=task_id, actor=user, status_code=status_code)
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/comments")
def task_comment_submit(request: Request, task_id: int, text: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task_service.add_comment_for_user(db, task_id=task_id, actor=user, text=text)
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/attachments")
async def task_attachment_submit(request: Request, task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), storage: StorageService = Depends(get_storage_service)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = task_service.get_task_for_user(db, task_id, user)
    data = await file.read()
    if data:
        object_key = storage.upload_bytes(filename=file.filename or "file", data=data, content_type=file.content_type)
        attachment = Attachment(task_id=task.id, uploaded_by_id=user.id, file_name=file.filename or "file", object_key=object_key, content_type=file.content_type, size_bytes=len(data))
        db.add(attachment)
        db.flush()
        write_audit_log(db, actor_id=user.id, entity_type="attachment", entity_id=attachment.id, action="upload_attachment", diff={"task_id": task.id, "file_name": attachment.file_name})
        db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)
