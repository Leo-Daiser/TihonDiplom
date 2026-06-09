from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.monitoring_event import MonitoringEvent
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter(tags=["web"])
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


def apply_task_scope(query, user: User):
    if user.role.code == "worker":
        return query.filter(or_(Task.assignee_id == user.id, Task.creator_id == user.id))
    return query


def get_task_for_user(db: Session, task_id: int, user: User) -> Task:
    task = (
        db.query(Task)
        .options(
            joinedload(Task.creator),
            joinedload(Task.assignee),
            joinedload(Task.status),
            joinedload(Task.priority),
            selectinload(Task.comments),
            selectinload(Task.attachments),
        )
        .filter(Task.id == task_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if user.role.code == "worker" and task.assignee_id != user.id and task.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return task


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).options(joinedload(User.role)).filter(User.email == email).first()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный email или пароль"}, status_code=400)
    token = create_access_token(subject=str(user.id))
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    base_query = apply_task_scope(db.query(Task), user)
    total_tasks = base_query.count()
    new_tasks = apply_task_scope(db.query(Task).join(Task.status).filter(TaskStatus.code == "new"), user).count()
    in_progress_tasks = apply_task_scope(db.query(Task).join(Task.status).filter(TaskStatus.code == "in_progress"), user).count()
    done_tasks = apply_task_scope(db.query(Task).join(Task.status).filter(TaskStatus.code == "done"), user).count()
    incident_tasks = apply_task_scope(db.query(Task).filter(Task.source_type == "zabbix"), user).count()
    recent_tasks = apply_task_scope(db.query(Task).options(joinedload(Task.assignee), joinedload(Task.status), joinedload(Task.priority)), user).order_by(Task.created_at.desc()).limit(6).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "stats": {"total": total_tasks, "new": new_tasks, "in_progress": in_progress_tasks, "done": done_tasks, "incidents": incident_tasks}, "recent_tasks": recent_tasks})


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, status_code: str | None = None, priority_code: str | None = None, source_type: str | None = None, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    query = db.query(Task).options(joinedload(Task.assignee), joinedload(Task.status), joinedload(Task.priority))
    query = apply_task_scope(query, user)
    if status_code:
        query = query.join(Task.status).filter(TaskStatus.code == status_code)
    if priority_code:
        query = query.join(Task.priority).filter(TaskPriority.code == priority_code)
    if source_type:
        query = query.filter(Task.source_type == source_type)
    tasks = query.order_by(Task.created_at.desc()).all()
    statuses = db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all()
    priorities = db.query(TaskPriority).order_by(TaskPriority.sort_order.asc()).all()
    return templates.TemplateResponse("tasks.html", {"request": request, "user": user, "tasks": tasks, "statuses": statuses, "priorities": priorities, "filters": {"status_code": status_code, "priority_code": priority_code, "source_type": source_type}, "can_manage": user_can_manage_tasks(user)})


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    if not user_can_manage_tasks(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse("task_form.html", {"request": request, "user": user, "statuses": db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all(), "priorities": db.query(TaskPriority).order_by(TaskPriority.sort_order.asc()).all(), "users": db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name.asc()).all()})


@router.post("/tasks/new")
def create_task_from_form(request: Request, title: str = Form(...), description: str | None = Form(default=None), assignee_id: int | None = Form(default=None), priority_code: str = Form("medium"), status_code: str = Form("new"), db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    if not user_can_manage_tasks(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    status_obj = db.query(TaskStatus).filter(TaskStatus.code == status_code).one()
    priority_obj = db.query(TaskPriority).filter(TaskPriority.code == priority_code).one()
    task = Task(title=title, description=description, creator_id=user.id, assignee_id=assignee_id, status_id=status_obj.id, priority_id=priority_obj.id, source_type="manual")
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
    return templates.TemplateResponse("task_detail.html", {"request": request, "user": user, "task": task, "statuses": statuses})


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


@router.get("/incidents", response_class=HTMLResponse)
def incidents_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    query = db.query(MonitoringEvent).options(joinedload(MonitoringEvent.task)).order_by(MonitoringEvent.received_at.desc())
    events = query.limit(100).all()
    return templates.TemplateResponse("incidents.html", {"request": request, "user": user, "events": events})


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    if user.role.code not in {"admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    entries = db.query(AuditLog).options(joinedload(AuditLog.actor)).order_by(AuditLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "entries": entries})
