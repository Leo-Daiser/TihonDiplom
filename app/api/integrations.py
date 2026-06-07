from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.monitoring_event import MonitoringEvent
from app.models.task import Task
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.schemas.integration import ZabbixWebhookPayload, ZabbixWebhookResponse
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
settings = get_settings()


SEVERITY_TO_PRIORITY = {
    "disaster": "critical",
    "critical": "critical",
    "high": "high",
    "average": "medium",
    "warning": "medium",
    "medium": "medium",
    "information": "low",
    "info": "low",
    "low": "low",
}


def check_integration_token(authorization: str | None) -> None:
    """Webhook принимает запрос только с ожидаемым Bearer-токеном."""
    expected = f"Bearer {settings.zabbix_webhook_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен интеграции")


def get_priority_for_severity(db: Session, severity: str | None) -> TaskPriority:
    severity_key = (severity or "low").lower()
    priority_code = SEVERITY_TO_PRIORITY.get(severity_key, "low")
    priority = db.query(TaskPriority).filter(TaskPriority.code == priority_code).one()
    return priority


def get_default_status(db: Session) -> TaskStatus:
    return db.query(TaskStatus).filter(TaskStatus.code == "new").one()


def get_system_user(db: Session) -> User:
    """Пока системным автором автоматических задач выступает администратор из seed-данных."""
    return db.query(User).filter(User.email == "admin@example.com").one()


def get_default_assignee(db: Session) -> User | None:
    return db.query(User).filter(User.email == "worker@example.com", User.is_active.is_(True)).first()


@router.post("/zabbix/webhook", response_model=ZabbixWebhookResponse)
def receive_zabbix_webhook(
    payload: ZabbixWebhookPayload,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ZabbixWebhookResponse:
    """Событие Zabbix сохраняется и при первом получении превращается в задачу-инцидент."""
    check_integration_token(authorization)

    existing_event = (
        db.query(MonitoringEvent)
        .filter(MonitoringEvent.source_system == "zabbix", MonitoringEvent.external_event_id == payload.event_id)
        .first()
    )
    if existing_event is not None:
        write_audit_log(
            db,
            actor_id=None,
            entity_type="monitoring_event",
            entity_id=existing_event.id,
            action="duplicate_zabbix_event",
            diff={"external_event_id": payload.event_id},
        )
        db.commit()
        return ZabbixWebhookResponse(status="duplicate", event_id=existing_event.id, task_id=existing_event.task_id, duplicate=True)

    priority = get_priority_for_severity(db, payload.severity)
    default_status = get_default_status(db)
    system_user = get_system_user(db)
    default_assignee = get_default_assignee(db)

    title_parts = ["Инцидент мониторинга"]
    if payload.host:
        title_parts.append(payload.host)
    if payload.trigger:
        title_parts.append(payload.trigger)

    task = Task(
        title=" — ".join(title_parts),
        description=f"Событие Zabbix: {payload.trigger or 'без описания'}",
        creator_id=system_user.id,
        assignee_id=default_assignee.id if default_assignee else None,
        status_id=default_status.id,
        priority_id=priority.id,
        source_type="zabbix",
    )
    db.add(task)
    db.flush()

    event = MonitoringEvent(
        task_id=task.id,
        source_system="zabbix",
        external_event_id=payload.event_id,
        host=payload.host,
        trigger_name=payload.trigger,
        severity=payload.severity,
        payload=payload.model_dump(mode="json"),
        status="received",
    )
    db.add(event)
    db.flush()

    write_audit_log(
        db,
        actor_id=None,
        entity_type="monitoring_event",
        entity_id=event.id,
        action="receive_zabbix_event",
        diff={"external_event_id": payload.event_id, "severity": payload.severity},
    )
    write_audit_log(
        db,
        actor_id=None,
        entity_type="task",
        entity_id=task.id,
        action="create_incident_task_from_zabbix",
        diff={"monitoring_event_id": event.id, "priority": priority.code},
    )
    db.commit()

    return ZabbixWebhookResponse(status="created", event_id=event.id, task_id=task.id, duplicate=False)
