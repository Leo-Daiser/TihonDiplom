from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse, RocketChatTestRequest, RocketChatTestResponse
from app.services.notification_service import send_rocketchat_payload

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> list[Notification]:
    """Журнал внешних уведомлений доступен администраторам и руководителям."""
    return db.query(Notification).order_by(Notification.created_at.desc()).limit(100).all()


@router.post("/rocketchat/test", response_model=RocketChatTestResponse)
def test_rocketchat_notification(
    payload: RocketChatTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> RocketChatTestResponse:
    """Проверочная отправка сообщения в Rocket.Chat webhook."""
    notification = send_rocketchat_payload(db, text=payload.text)
    db.commit()
    return RocketChatTestResponse(
        notification_id=notification.id,
        status=notification.status,
        response=notification.response,
    )
