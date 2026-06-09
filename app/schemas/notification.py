from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    channel: str
    recipient: str | None
    status: str
    payload: dict | None
    response: str | None
    created_at: datetime
    sent_at: datetime | None


class RocketChatTestRequest(BaseModel):
    text: str = Field(default="Тестовое уведомление из IT Workflow", min_length=1, max_length=1000)


class RocketChatTestResponse(BaseModel):
    notification_id: int
    status: str
    response: str | None
