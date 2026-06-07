from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TaskPriorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TaskUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str


class TaskCreateRequest(BaseModel):
    """Данные для создания задачи через API."""

    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    assignee_id: int | None = None
    status_code: str = "new"
    priority_code: str = "medium"
    deadline: datetime | None = None


class TaskUpdateRequest(BaseModel):
    """При обновлении передаются только поля, которые нужно изменить."""

    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    assignee_id: int | None = None
    status_code: str | None = None
    priority_code: str | None = None
    deadline: datetime | None = None


class TaskCommentCreateRequest(BaseModel):
    """Текст комментария к задаче."""

    text: str = Field(min_length=1)


class TaskCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    author_id: int
    text: str
    created_at: datetime


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    creator: TaskUserResponse
    assignee: TaskUserResponse | None
    status: TaskStatusResponse
    priority: TaskPriorityResponse
    source_type: str
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskDetailResponse(TaskResponse):
    comments: list[TaskCommentResponse]
