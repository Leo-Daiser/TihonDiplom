from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ZabbixWebhookPayload(BaseModel):
    """Payload Zabbix нормализуется из разных вариантов имен полей и не падает на лишних ключах."""

    model_config = ConfigDict(extra="allow")

    event_id: str | None = Field(default=None, max_length=255)
    host: str | None = None
    trigger: str | None = None
    severity: str | None = None
    subject: str | None = None
    message: str | None = None
    timestamp: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_zabbix_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        def first_value(*keys: str) -> Any:
            for key in keys:
                value = data.get(key)
                if value not in (None, ""):
                    return value
            return None

        normalized = dict(data)
        normalized["event_id"] = first_value("event_id", "eventid", "event.id", "eventId", "EVENT.ID")
        normalized["host"] = first_value("host", "host_name", "hostname", "host.name", "HOST.NAME")
        normalized["trigger"] = first_value("trigger", "trigger_name", "trigger.description", "TRIGGER.NAME", "ALERT.SUBJECT")
        normalized["severity"] = first_value("severity", "event_severity", "trigger_severity", "event.severity", "TRIGGER.SEVERITY")
        normalized["subject"] = first_value("subject", "alert_subject", "ALERT.SUBJECT")
        normalized["message"] = first_value("message", "alert_message", "ALERT.MESSAGE")
        normalized["timestamp"] = first_value("timestamp", "event_time", "event.clock", "EVENT.TIME")
        return normalized


class ZabbixWebhookResponse(BaseModel):
    status: str
    event_id: int
    task_id: int | None = None
    duplicate: bool = False
