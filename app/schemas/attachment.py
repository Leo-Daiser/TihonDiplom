from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    uploaded_by_id: int
    file_name: str
    content_type: str | None
    size_bytes: int
    created_at: datetime


class AttachmentDownloadResponse(BaseModel):
    url: str
