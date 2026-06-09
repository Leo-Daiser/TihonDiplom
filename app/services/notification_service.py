from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.notification import Notification
from app.models.task import Task

settings = get_settings()


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


def send_rocketchat_payload(db: Session, *, text: str, task_id: int | None = None) -> Notification:
    """Отправляет сообщение в Rocket.Chat Incoming Webhook и фиксирует результат в БД."""
    payload = {"text": text}
    recipient = settings.rocketchat_webhook_url or "rocketchat-webhook"

    if not settings.rocketchat_enabled:
        return create_notification(
            db,
            channel="rocketchat",
            task_id=task_id,
            recipient=recipient,
            status="skipped",
            payload=payload,
            response="Rocket.Chat integration is disabled",
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


def build_task_notification_text(task: Task, *, event: str) -> str:
    """Формирует короткое сообщение о задаче для внешнего канала."""
    parts = [f"{event}: задача #{task.id}", f"Название: {task.title}"]
    if task.priority:
        parts.append(f"Приоритет: {task.priority.name}")
    if task.status:
        parts.append(f"Статус: {task.status.name}")
    if task.assignee:
        parts.append(f"Исполнитель: {task.assignee.full_name}")
    return "\n".join(parts)


def notify_task_event(db: Session, *, task: Task, event: str) -> Notification:
    """Отправляет уведомление о событии задачи в Rocket.Chat."""
    return send_rocketchat_payload(db, text=build_task_notification_text(task, event=event), task_id=task.id)
