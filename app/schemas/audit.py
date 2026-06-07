from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditActorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: AuditActorResponse | None
    entity_type: str
    entity_id: int | None
    action: str
    diff: dict | None
    created_at: datetime
