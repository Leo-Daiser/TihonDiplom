from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.task import Task
from app.models.task_comment import TaskComment
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.services.audit_service import write_audit_log


def user_can_manage_tasks(user: User) -> bool:
    """Администратор и руководитель управляют задачами, исполнитель работает только со своими."""
    return user.role.code in {"admin", "manager"}


def require_task_manager(user: User) -> None:
    if not user_can_manage_tasks(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для управления задачами")


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


def task_query(db: Session, *, include_attachments: bool = False):
    """Базовая ORM-загрузка задачи для API и web-страниц."""
    options = [
        joinedload(Task.creator),
        joinedload(Task.assignee),
        joinedload(Task.status),
        joinedload(Task.priority),
        selectinload(Task.comments).joinedload(TaskComment.author),
    ]
    if include_attachments:
        options.append(selectinload(Task.attachments))
    return db.query(Task).options(*options)


def apply_task_scope(query, user: User):
    """Исполнитель видит только задачи, которые он создал или которые ему назначены."""
    if user.role.code == "worker":
        return query.filter(or_(Task.assignee_id == user.id, Task.creator_id == user.id))
    return query


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
    """Общие фильтры задач для JSON API и web-интерфейса."""
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


def ensure_task_access(task: Task | None, current_user: User) -> None:
    """Проверяет доступ к задаче, не меняя ее состояние."""
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    if user_can_manage_tasks(current_user):
        return
    if task.assignee_id == current_user.id or task.creator_id == current_user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к задаче")


def get_task_or_404(db: Session, task_id: int, *, include_attachments: bool = False) -> Task:
    task = task_query(db, include_attachments=include_attachments).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return task


def get_task_for_user(db: Session, task_id: int, user: User, *, include_attachments: bool = False) -> Task:
    task = get_task_or_404(db, task_id, include_attachments=include_attachments)
    ensure_task_access(task, user)
    return task


def list_tasks_for_user(
    db: Session,
    user: User,
    *,
    q: str | None = None,
    status_code: str | None = None,
    priority_code: str | None = None,
    assignee_id: int | None = None,
    source_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[Task]:
    query = apply_task_scope(task_query(db), user)
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


def create_task_record(
    db: Session,
    *,
    actor: User,
    title: str,
    description: str | None,
    assignee_id: int | None,
    status_code: str,
    priority_code: str,
    deadline: datetime | None = None,
    source_type: str = "manual",
) -> Task:
    status_obj = get_status_by_code(db, status_code)
    priority_obj = get_priority_by_code(db, priority_code)
    get_user_or_none(db, assignee_id)

    task = Task(
        title=title,
        description=description,
        creator_id=actor.id,
        assignee_id=assignee_id,
        status_id=status_obj.id,
        priority_id=priority_obj.id,
        source_type=source_type,
        deadline=deadline,
    )
    db.add(task)
    db.flush()
    write_audit_log(
        db,
        actor_id=actor.id,
        entity_type="task",
        entity_id=task.id,
        action="create_task",
        diff={"title": task.title, "assignee_id": task.assignee_id, "status": status_obj.code, "priority": priority_obj.code},
    )
    db.commit()
    return get_task_or_404(db, task.id)


def update_task_record(db: Session, *, task: Task, actor: User, data: dict[str, Any]) -> Task:
    changes: dict[str, Any] = {}

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
    if data.get("status_code") is not None:
        status_obj = get_status_by_code(db, data["status_code"])
        if status_obj.id != task.status_id:
            changes["status"] = {"old": task.status.code, "new": status_obj.code}
            task.status_id = status_obj.id
    if data.get("priority_code") is not None:
        priority_obj = get_priority_by_code(db, data["priority_code"])
        if priority_obj.id != task.priority_id:
            changes["priority"] = {"old": task.priority.code, "new": priority_obj.code}
            task.priority_id = priority_obj.id
    if "deadline" in data and data["deadline"] != task.deadline:
        changes["deadline"] = {"old": str(task.deadline), "new": str(data["deadline"])}
        task.deadline = data["deadline"]

    if changes:
        write_audit_log(db, actor_id=actor.id, entity_type="task", entity_id=task.id, action="update_task", diff=changes)
    db.commit()
    return get_task_or_404(db, task.id)


def change_task_status_for_user(db: Session, *, task_id: int, actor: User, status_code: str) -> Task:
    task = get_task_for_user(db, task_id, actor)
    status_obj = get_status_by_code(db, status_code)
    if status_obj.id != task.status_id:
        old_status = task.status.code
        task.status_id = status_obj.id
        write_audit_log(
            db,
            actor_id=actor.id,
            entity_type="task",
            entity_id=task.id,
            action="update_task_status",
            diff={"status": {"old": old_status, "new": status_obj.code}},
        )
    db.commit()
    return get_task_or_404(db, task.id)


def add_comment_for_user(db: Session, *, task_id: int, actor: User, text: str) -> TaskComment:
    task = get_task_for_user(db, task_id, actor)
    comment = TaskComment(task_id=task.id, author_id=actor.id, text=text)
    db.add(comment)
    db.flush()
    write_audit_log(
        db,
        actor_id=actor.id,
        entity_type="task_comment",
        entity_id=comment.id,
        action="create_task_comment",
        diff={"task_id": task.id},
    )
    db.commit()
    db.refresh(comment)
    return comment
