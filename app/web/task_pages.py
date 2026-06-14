from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter(tags=["web-tasks"])
templates = Jinja2Templates(directory="app/templates")


def redirect_to_login() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


def get_user_from_cookie(request: Request, db: Session) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        return None
    return db.query(User).options(joinedload(User.role)).filter(User.id == user_id, User.is_active.is_(True)).first()


def user_can_manage_tasks(user: User) -> bool:
    return user.role.code in {"admin", "manager"}


def require_task_manager(user: User) -> None:
    if not user_can_manage_tasks(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def apply_task_scope(query, user: User):
    if user.role.code == "worker":
        return query.filter(or_(Task.assignee_id == user.id, Task.creator_id == user.id))
    return query


def task_query(db: Session):
    return db.query(Task).options(
        joinedload(Task.creator),
        joinedload(Task.assignee),
        joinedload(Task.status),
        joinedload(Task.priority),
        selectinload(Task.comments).joinedload(TaskComment.author),
        selectinload(Task.attachments),
    )


def get_task_for_user(db: Session, task_id: int, user: User) -> Task:
    task = task_query(db).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if user.role.code == "worker" and task.assignee_id != user.id and task.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return task


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
    query = apply_task_scope(task_query(db), user)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Task.title.ilike(like), Task.description.ilike(like)))
    if status_code:
        query = query.join(Task.status).filter(TaskStatus.code == status_code)
    if priority_code:
        query = query.join(Task.priority).filter(TaskPriority.code == priority_code)
    if assignee_filter is not None:
        query = query.filter(Task.assignee_id == assignee_filter)
    if source_type:
        query = query.filter(Task.source_type == source_type)
    context = form_context(request, user, db, tasks=query.order_by(Task.created_at.desc()).all(), filters={"q": q, "status_code": status_code, "priority_code": priority_code, "assignee_id": assignee_filter, "source_type": source_type}, can_manage=user_can_manage_tasks(user))
    return templates.TemplateResponse(request, "tasks.html", context)


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    require_task_manager(user)
    context = form_context(request, user, db, task=None, page_title="Новая задача", form_action="/tasks/new", submit_label="Создать задачу")
    return templates.TemplateResponse(request, "task_form.html", context)


@router.post("/tasks/new")
def create_task_from_form(request: Request, title: str = Form(...), description: str | None = Form(default=None), assignee_id: str | None = Form(default=None), priority_code: str = Form("medium"), status_code: str = Form("new"), deadline: str | None = Form(default=None), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    require_task_manager(user)
    status_obj = db.query(TaskStatus).filter(TaskStatus.code == status_code).one()
    priority_obj = db.query(TaskPriority).filter(TaskPriority.code == priority_code).one()
    task = Task(title=title, description=description, creator_id=user.id, assignee_id=parse_optional_int(assignee_id), status_id=status_obj.id, priority_id=priority_obj.id, source_type="manual", deadline=parse_deadline(deadline))
    db.add(task)
    db.flush()
    write_audit_log(db, actor_id=user.id, entity_type="task", entity_id=task.id, action="create_task", diff={"title": title})
    db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail_page(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = get_task_for_user(db, task_id, user)
    statuses = db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all()
    context = {"request": request, "user": user, "task": task, "statuses": statuses, "can_manage": user_can_manage_tasks(user)}
    return templates.TemplateResponse(request, "task_detail.html", context)


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_page(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    require_task_manager(user)
    task = get_task_for_user(db, task_id, user)
    context = form_context(request, user, db, task=task, page_title=f"Редактирование задачи #{task.id}", form_action=f"/tasks/{task.id}/edit", submit_label="Сохранить изменения")
    return templates.TemplateResponse(request, "task_form.html", context)


@router.post("/tasks/{task_id}/edit")
def edit_task_submit(request: Request, task_id: int, title: str = Form(...), description: str | None = Form(default=None), assignee_id: str | None = Form(default=None), priority_code: str = Form(...), status_code: str = Form(...), deadline: str | None = Form(default=None), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    require_task_manager(user)
    task = get_task_for_user(db, task_id, user)
    status_obj = db.query(TaskStatus).filter(TaskStatus.code == status_code).one()
    priority_obj = db.query(TaskPriority).filter(TaskPriority.code == priority_code).one()
    new_assignee_id = parse_optional_int(assignee_id)
    new_deadline = parse_deadline(deadline)
    changes = {}
    if title != task.title:
        changes["title"] = {"old": task.title, "new": title}
        task.title = title
    if description != task.description:
        changes["description"] = {"old": task.description, "new": description}
        task.description = description
    if new_assignee_id != task.assignee_id:
        changes["assignee_id"] = {"old": task.assignee_id, "new": new_assignee_id}
        task.assignee_id = new_assignee_id
    if status_obj.id != task.status_id:
        changes["status"] = {"old": task.status.code, "new": status_obj.code}
        task.status_id = status_obj.id
    if priority_obj.id != task.priority_id:
        changes["priority"] = {"old": task.priority.code, "new": priority_obj.code}
        task.priority_id = priority_obj.id
    if new_deadline != task.deadline:
        changes["deadline"] = {"old": str(task.deadline), "new": str(new_deadline)}
        task.deadline = new_deadline
    if changes:
        write_audit_log(db, actor_id=user.id, entity_type="task", entity_id=task.id, action="update_task", diff=changes)
    db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/status")
def task_status_submit(request: Request, task_id: int, status_code: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = get_task_for_user(db, task_id, user)
    status_obj = db.query(TaskStatus).filter(TaskStatus.code == status_code).one()
    if status_obj.id != task.status_id:
        old_status = task.status.code
        task.status_id = status_obj.id
        write_audit_log(db, actor_id=user.id, entity_type="task", entity_id=task.id, action="update_task_status", diff={"status": {"old": old_status, "new": status_obj.code}})
        db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/comments")
def task_comment_submit(request: Request, task_id: int, text: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = get_task_for_user(db, task_id, user)
    comment = TaskComment(task_id=task.id, author_id=user.id, text=text)
    db.add(comment)
    db.flush()
    write_audit_log(db, actor_id=user.id, entity_type="task_comment", entity_id=comment.id, action="create_task_comment", diff={"task_id": task.id})
    db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/attachments")
async def task_attachment_submit(request: Request, task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), storage: StorageService = Depends(get_storage_service)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    task = get_task_for_user(db, task_id, user)
    data = await file.read()
    if data:
        object_key = storage.upload_bytes(filename=file.filename or "file", data=data, content_type=file.content_type)
        attachment = Attachment(task_id=task.id, uploaded_by_id=user.id, file_name=file.filename or "file", object_key=object_key, content_type=file.content_type, size_bytes=len(data))
        db.add(attachment)
        db.flush()
        write_audit_log(db, actor_id=user.id, entity_type="attachment", entity_id=attachment.id, action="upload_attachment", diff={"task_id": task.id, "file_name": attachment.file_name})
        db.commit()
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)
