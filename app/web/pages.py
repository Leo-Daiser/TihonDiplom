from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.monitoring_event import MonitoringEvent
from app.models.task import Task
from app.models.task_status import TaskStatus
from app.models.user import User
from app.web.deps import get_user_from_cookie, redirect_to_login, require_web_manager_or_admin

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


def apply_task_scope(query, user: User):
    if user.role.code == "worker":
        return query.filter((Task.assignee_id == user.id) | (Task.creator_id == user.id))
    return query


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
    user = require_web_manager_or_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user
    entries = db.query(AuditLog).options(joinedload(AuditLog.actor)).order_by(AuditLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "entries": entries})
