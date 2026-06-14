from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.schemas.task import TaskCommentCreateRequest, TaskCommentResponse, TaskCreateRequest, TaskDetailResponse, TaskResponse, TaskUpdateRequest
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def get_status_by_code(db: Session, code: str) -> TaskStatus:
    status_obj = db.query(TaskStatus).filter(TaskStatus.code == code).first()
    if status_obj is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный статус задачи")
    return status_obj


def get_priority_by_code(db: Session, code: str) -> TaskPriority:
    priority_obj = db.query(TaskPriority).filter(TaskPriority.code == code).first()
    if priority_obj is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный приоритет задачи")
    return priority_obj


def get_user_or_none(db: Session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Исполнитель не найден или отключен")
    return user


def build_task_query(db: Session):
    """Одинаковая загрузка связей нужна для списка задач и карточки задачи."""
    return db.query(Task).options(
        joinedload(Task.creator),
        joinedload(Task.assignee),
        joinedload(Task.status),
        joinedload(Task.priority),
        selectinload(Task.comments),
    )


def ensure_task_access(task: Task, current_user: User) -> None:
    """Исполнитель видит свои задачи, руководитель и администратор видят все задачи."""
    role_code = current_user.role.code
    if role_code in {"admin", "manager"}:
        return
    if task.assignee_id == current_user.id or task.creator_id == current_user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к задаче")


def apply_task_filters(
    query,
    *,
    q: str | None = None,
    status_code: str | None = None,
    priority_code: str | None = None,
    assignee_id: int | None = None,
    source_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
):
    """Фильтры задач используются и API, и web-страницами."""
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(or_(Task.title.ilike(search), Task.description.ilike(search)))
    if status_code:
        query = query.join(Task.status).filter(TaskStatus.code == status_code)
    if priority_code:
        query = query.join(Task.priority).filter(TaskPriority.code == priority_code)
    if assignee_id is not None:
        query = query.filter(Task.assignee_id == assignee_id)
    if source_type:
        query = query.filter(Task.source_type == source_type)
    if created_from is not None:
        query = query.filter(Task.created_at >= created_from)
    if created_to is not None:
        query = query.filter(Task.created_at <= created_to)
    return query


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
    query = build_task_query(db)

    if current_user.role.code == "worker":
        query = query.filter((Task.assignee_id == current_user.id) | (Task.creator_id == current_user.id))
    query = apply_task_filters(
        query,
        q=q,
        status_code=status_code,
        priority_code=priority_code,
        assignee_id=assignee_id,
        source_type=source_type,
        created_from=created_from,
        created_to=created_to,
    )

    return query.order_by(Task.created_at.desc()).all()


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> Task:
    """Задачу создают администратор или руководитель, автором фиксируется текущий пользователь."""
    status_obj = get_status_by_code(db, payload.status_code)
    priority_obj = get_priority_by_code(db, payload.priority_code)
    get_user_or_none(db, payload.assignee_id)

    task = Task(
        title=payload.title,
        description=payload.description,
        creator_id=current_user.id,
        assignee_id=payload.assignee_id,
        status_id=status_obj.id,
        priority_id=priority_obj.id,
        source_type="manual",
        deadline=payload.deadline,
    )
    db.add(task)
    db.flush()
    write_audit_log(
        db,
        actor_id=current_user.id,
        entity_type="task",
        entity_id=task.id,
        action="create_task",
        diff={"title": task.title, "assignee_id": task.assignee_id, "status": status_obj.code, "priority": priority_obj.code},
    )
    db.commit()
    return build_task_query(db).filter(Task.id == task.id).one()


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Карточка задачи возвращает основные поля и комментарии."""
    task = build_task_query(db).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    ensure_task_access(task, current_user)
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> Task:
    """Обновление задачи пока доступно администратору и руководителю."""
    task = build_task_query(db).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

    changes: dict = {}
    data = payload.model_dump(exclude_unset=True)

    if "title" in data and data["title"] != task.title:
        changes["title"] = {"old": task.title, "new": data["title"]}
        task.title = data["title"]
    if "description" in data and data["description"] != task.description:
        changes["description"] = {"old": task.description, "new": data["description"]}
        task.description = data["description"]
    if "assignee_id" in data and data["assignee_id"] != task.assignee_id:
        get_user_or_none(db, data["assignee_id"])
        changes["assignee_id"] = {"old": task.assignee_id, "new": data["assignee_id"]}
        task.assignee_id = data["assignee_id"]
    if "status_code" in data and data["status_code"] is not None:
        status_obj = get_status_by_code(db, data["status_code"])
        if status_obj.id != task.status_id:
            changes["status"] = {"old": task.status.code, "new": status_obj.code}
            task.status_id = status_obj.id
    if "priority_code" in data and data["priority_code"] is not None:
        priority_obj = get_priority_by_code(db, data["priority_code"])
        if priority_obj.id != task.priority_id:
            changes["priority"] = {"old": task.priority.code, "new": priority_obj.code}
            task.priority_id = priority_obj.id
    if "deadline" in data and data["deadline"] != task.deadline:
        changes["deadline"] = {"old": str(task.deadline), "new": str(data["deadline"])}
        task.deadline = data["deadline"]

    if changes:
        write_audit_log(db, actor_id=current_user.id, entity_type="task", entity_id=task.id, action="update_task", diff=changes)

    db.commit()
    return build_task_query(db).filter(Task.id == task.id).one()


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: int,
    status_code: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Исполнитель может менять статус доступной ему задачи, остальные права проверяются через доступ к карточке."""
    task = build_task_query(db).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    ensure_task_access(task, current_user)

    status_obj = get_status_by_code(db, status_code)
    if status_obj.id != task.status_id:
        old_status = task.status.code
        task.status_id = status_obj.id
        write_audit_log(
            db,
            actor_id=current_user.id,
            entity_type="task",
            entity_id=task.id,
            action="update_task_status",
            diff={"status": {"old": old_status, "new": status_obj.code}},
        )

    db.commit()
    return build_task_query(db).filter(Task.id == task.id).one()


@router.post("/{task_id}/comments", response_model=TaskCommentResponse, status_code=status.HTTP_201_CREATED)
def add_comment(
    task_id: int,
    payload: TaskCommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskComment:
    """Комментарий можно добавить только к задаче, к которой есть доступ."""
    task = build_task_query(db).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    ensure_task_access(task, current_user)

    comment = TaskComment(task_id=task.id, author_id=current_user.id, text=payload.text)
    db.add(comment)
    db.flush()
    write_audit_log(
        db,
        actor_id=current_user.id,
        entity_type="task_comment",
        entity_id=comment.id,
        action="create_task_comment",
        diff={"task_id": task.id},
    )
    db.commit()
    db.refresh(comment)
    return comment
