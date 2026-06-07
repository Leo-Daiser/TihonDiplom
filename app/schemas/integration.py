from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ZabbixWebhookPayload(BaseModel):
    """Минимальный payload события мониторинга, достаточный для создания задачи-инцидента."""

    event_id: str = Field(min_length=1, max_length=255)
    host: str | None = None
    trigger: str | None = None
    severity: str | None = None
    timestamp: datetime | None = None


class ZabbixWebhookResponse(BaseModel):
    status: str
    event_id: int
    task_id: int | None = None
    duplicate: bool = False
