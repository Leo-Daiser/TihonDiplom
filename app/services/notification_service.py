from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.notification import Notification
from app.models.task import Task

settings = get_settings()


PRIORITY_COLORS = {
    "critical": "#d73a49",
    "high": "#e36209",
    "medium": "#dbab09",
    "low": "#2f81f7",
}


def create_notification(
    db: Session,
    *,
    channel: str,
    payload: dict,
    task_id: int | None = None,
    recipient: str | None = None,
    status: str = "pending",
    response: str | None = None,
) -> Notification:
    """Единая точка создания записей о внешних уведомлениях."""
    notification = Notification(
        task_id=task_id,
        channel=channel,
        recipient=recipient,
        status=status,
        payload=payload,
        response=response,
    )
    db.add(notification)
    db.flush()
    return notification


def send_rocketchat_payload(db: Session, *, payload: dict, task_id: int | None = None) -> Notification:
    """Отправляет готовый Rocket.Chat payload в Incoming Webhook и фиксирует результат в БД."""
    recipient = settings.rocketchat_webhook_url or "rocketchat-webhook"

    if not settings.rocketchat_enabled:
        return create_notification(
            db,
            channel="rocketchat",
            task_id=task_id,
            recipient=recipient,
            status="skipped",
            payload=payload,
            response="RocketChat integration is disabled",
        )

    if not settings.rocketchat_webhook_url:
        return create_notification(
            db,
            channel="rocketchat",
            task_id=task_id,
            recipient=recipient,
            status="failed",
            payload=payload,
            response="ROCKETCHAT_WEBHOOK_URL is empty",
        )

    notification = create_notification(
        db,
        channel="rocketchat",
        task_id=task_id,
        recipient=recipient,
        status="pending",
        payload=payload,
    )

    try:
        result = httpx.post(settings.rocketchat_webhook_url, json=payload, timeout=10.0)
        notification.response = result.text[:4000]
        notification.status = "sent" if 200 <= result.status_code < 300 else "failed"
        notification.sent_at = datetime.now(timezone.utc)
    except Exception as exc:
        notification.status = "failed"
        notification.response = str(exc)[:4000]
        notification.sent_at = datetime.now(timezone.utc)

    db.flush()
    return notification


def build_task_rocketchat_payload(task: Task, *, event: str) -> dict:
    """Формирует структурированное сообщение Rocket.Chat: text + attachment fields."""
    priority_code = task.priority.code if task.priority else "low"
    priority_name = task.priority.name if task.priority else "Не указан"
    status_name = task.status.name if task.status else "Не указан"
    assignee = task.assignee.full_name if task.assignee else "Не назначен"

    return {
        "alias": "IT Workflow",
        "emoji": ":warning:",
        "text": f"{event}: задача #{task.id}",
        "attachments": [
            {
                "color": PRIORITY_COLORS.get(priority_code, "#2f81f7"),
                "title": task.title,
                "text": task.description or "Описание не указано",
                "fields": [
                    {"title": "ID задачи", "value": str(task.id), "short": True},
                    {"title": "Приоритет", "value": priority_name, "short": True},
                    {"title": "Статус", "value": status_name, "short": True},
                    {"title": "Исполнитель", "value": assignee, "short": True},
                    {"title": "Источник", "value": task.source_type, "short": True},
                ],
            }
        ],
    }


def notify_task_event(db: Session, *, task: Task, event: str) -> Notification:
    """Отправляет уведомление о событии задачи в Rocket.Chat."""
    payload = build_task_rocketchat_payload(task, event=event)
    return send_rocketchat_payload(db, payload=payload, task_id=task.id)
