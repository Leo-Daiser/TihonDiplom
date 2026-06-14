import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.monitoring_event import MonitoringEvent
from app.models.task import Task
from app.web.deps import require_web_manager_or_admin

router = APIRouter(tags=["web-reports"])


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def build_csv_response(filename: str, rows: list[list[str]]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerows(rows)
    content = "\ufeff" + buffer.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/reports/tasks.csv")
def export_tasks_csv(request: Request, db: Session = Depends(get_db)):
    user = require_web_manager_or_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user
    tasks = (
        db.query(Task)
        .options(joinedload(Task.creator), joinedload(Task.assignee), joinedload(Task.status), joinedload(Task.priority))
        .order_by(Task.created_at.desc())
        .all()
    )
    rows = [["id", "title", "status", "priority", "source", "creator", "assignee", "deadline", "created_at", "updated_at"]]
    for task in tasks:
        rows.append([
            str(task.id),
            task.title,
            task.status.name if task.status else "",
            task.priority.name if task.priority else "",
            task.source_type,
            task.creator.full_name if task.creator else "",
            task.assignee.full_name if task.assignee else "",
            format_datetime(task.deadline),
            format_datetime(task.created_at),
            format_datetime(task.updated_at),
        ])
    return build_csv_response("tasks_report.csv", rows)


@router.get("/reports/incidents.csv")
def export_incidents_csv(request: Request, db: Session = Depends(get_db)):
    user = require_web_manager_or_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user
    events = db.query(MonitoringEvent).options(joinedload(MonitoringEvent.task)).order_by(MonitoringEvent.received_at.desc()).all()
    rows = [["id", "external_event_id", "host", "trigger", "severity", "status", "task_id", "received_at"]]
    for event in events:
        rows.append([
            str(event.id),
            event.external_event_id,
            event.host or "",
            event.trigger_name or "",
            event.severity or "",
            event.status,
            str(event.task_id or ""),
            format_datetime(event.received_at),
        ])
    return build_csv_response("incidents_report.csv", rows)
