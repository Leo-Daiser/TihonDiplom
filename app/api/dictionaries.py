from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User
from app.schemas.dictionary import DictionaryItemCreateRequest, DictionaryItemUpdateRequest, PriorityResponse, StatusResponse
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api/v1/admin/dictionaries", tags=["admin-dictionaries"])


@router.get("/statuses", response_model=list[StatusResponse])
def list_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> list[TaskStatus]:
    """Статусы читают администратор и руководитель, потому что они нужны при работе с задачами."""
    return db.query(TaskStatus).order_by(TaskStatus.sort_order.asc()).all()


@router.post("/statuses", response_model=StatusResponse, status_code=status.HTTP_201_CREATED)
def create_status(
    payload: DictionaryItemCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> TaskStatus:
    """Создание нового статуса оставлено за администратором."""
    if db.query(TaskStatus).filter(TaskStatus.code == payload.code).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Статус с таким кодом уже существует")
    status_obj = TaskStatus(
        code=payload.code,
        name=payload.name,
        sort_order=payload.sort_order,
        is_final=bool(payload.is_final),
        is_system=False,
    )
    db.add(status_obj)
    db.flush()
    write_audit_log(db, actor_id=current_user.id, entity_type="task_status", entity_id=status_obj.id, action="create_task_status", diff={"code": status_obj.code})
    db.commit()
    db.refresh(status_obj)
    return status_obj


@router.patch("/statuses/{status_id}", response_model=StatusResponse)
def update_status(
    status_id: int,
    payload: DictionaryItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> TaskStatus:
    """Системные и пользовательские статусы можно переименовывать, но код остается стабильным ключом."""
    status_obj = db.get(TaskStatus, status_id)
    if status_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статус не найден")

    data = payload.model_dump(exclude_unset=True)
    changes: dict = {}
    if "name" in data and data["name"] != status_obj.name:
        changes["name"] = {"old": status_obj.name, "new": data["name"]}
        status_obj.name = data["name"]
    if "sort_order" in data and data["sort_order"] != status_obj.sort_order:
        changes["sort_order"] = {"old": status_obj.sort_order, "new": data["sort_order"]}
        status_obj.sort_order = data["sort_order"]
    if "is_final" in data and data["is_final"] != status_obj.is_final:
        changes["is_final"] = {"old": status_obj.is_final, "new": data["is_final"]}
        status_obj.is_final = data["is_final"]

    if changes:
        write_audit_log(db, actor_id=current_user.id, entity_type="task_status", entity_id=status_obj.id, action="update_task_status_dictionary", diff=changes)
    db.commit()
    db.refresh(status_obj)
    return status_obj


@router.get("/priorities", response_model=list[PriorityResponse])
def list_priorities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
) -> list[TaskPriority]:
    """Приоритеты читают администратор и руководитель."""
    return db.query(TaskPriority).order_by(TaskPriority.sort_order.asc()).all()


@router.post("/priorities", response_model=PriorityResponse, status_code=status.HTTP_201_CREATED)
def create_priority(
    payload: DictionaryItemCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> TaskPriority:
    """Создание нового приоритета оставлено за администратором."""
    if db.query(TaskPriority).filter(TaskPriority.code == payload.code).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Приоритет с таким кодом уже существует")
    priority = TaskPriority(code=payload.code, name=payload.name, sort_order=payload.sort_order, is_system=False)
    db.add(priority)
    db.flush()
    write_audit_log(db, actor_id=current_user.id, entity_type="task_priority", entity_id=priority.id, action="create_task_priority", diff={"code": priority.code})
    db.commit()
    db.refresh(priority)
    return priority


@router.patch("/priorities/{priority_id}", response_model=PriorityResponse)
def update_priority(
    priority_id: int,
    payload: DictionaryItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> TaskPriority:
    """Код приоритета не меняется, чтобы существующие задачи не теряли связь со справочником."""
    priority = db.get(TaskPriority, priority_id)
    if priority is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приоритет не найден")

    data = payload.model_dump(exclude_unset=True)
    changes: dict = {}
    if "name" in data and data["name"] != priority.name:
        changes["name"] = {"old": priority.name, "new": data["name"]}
        priority.name = data["name"]
    if "sort_order" in data and data["sort_order"] != priority.sort_order:
        changes["sort_order"] = {"old": priority.sort_order, "new": data["sort_order"]}
        priority.sort_order = data["sort_order"]

    if changes:
        write_audit_log(db, actor_id=current_user.id, entity_type="task_priority", entity_id=priority.id, action="update_task_priority_dictionary", diff=changes)
    db.commit()
    db.refresh(priority)
    return priority
