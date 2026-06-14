from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.user import User
from app.schemas.task import TaskCommentCreateRequest, TaskCommentResponse, TaskCreateRequest, TaskDetailResponse, TaskResponse, TaskUpdateRequest
from app.services import task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    q: str | None = Query(default=None),
    status_code: str | None = Query(default=None),
    priority_code: str | None = Query(default=None),
    assignee_id: int | None = Query(default=None),
    source_type: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Task]:
    """Список задач фильтруется по основным полям, для исполнителя дополнительно ограничивается его задачами."""
    return task_service.list_tasks_for_user(
        db,
        current_user,
        q=q,
        status_code=status_code,
        priority_code=priority_code,
        assignee_id=assignee_id,
        source_type=source_type,
        created_from=created_from,
        created_to=created_to,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> Task:
    """Задачу создают администратор или руководитель, автором фиксируется текущий пользователь."""
    return task_service.create_task_record(
        db,
        actor=current_user,
        title=payload.title,
        description=payload.description,
        assignee_id=payload.assignee_id,
        status_code=payload.status_code,
        priority_code=payload.priority_code,
        deadline=payload.deadline,
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Карточка задачи возвращает основные поля и комментарии."""
    return task_service.get_task_for_user(db, task_id, current_user)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> Task:
    """Обновление задачи доступно администратору и руководителю."""
    task = task_service.get_task_or_404(db, task_id)
    return task_service.update_task_record(db, task=task, actor=current_user, data=payload.model_dump(exclude_unset=True))


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: int,
    status_code: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Исполнитель может менять статус доступной ему задачи, остальные права проверяются через доступ к карточке."""
    return task_service.change_task_status_for_user(db, task_id=task_id, actor=current_user, status_code=status_code)


@router.post("/{task_id}/comments", response_model=TaskCommentResponse, status_code=status.HTTP_201_CREATED)
def add_comment(
    task_id: int,
    payload: TaskCommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskComment:
    """Комментарий можно добавить только к задаче, к которой есть доступ."""
    return task_service.add_comment_for_user(db, task_id=task_id, actor=current_user, text=payload.text)
