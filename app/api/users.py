from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserCreateRequest, UserResponse, UserUpdateRequest
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


def get_role_by_code(db: Session, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестная роль")
    return role


def build_user_query(db: Session):
    """Пользователи сразу загружаются с ролью, чтобы ответ API был полным."""
    return db.query(User).options(joinedload(User.role))


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> list[User]:
    """Список пользователей доступен только администратору."""
    return build_user_query(db).order_by(User.id.asc()).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> User:
    """Администратор создает пользователя и сразу назначает ему роль."""
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует")

    role = get_role_by_code(db, payload.role_code)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=role.id,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    write_audit_log(
        db,
        actor_id=current_user.id,
        entity_type="user",
        entity_id=user.id,
        action="create_user",
        diff={"email": user.email, "role": role.code, "is_active": user.is_active},
    )
    db.commit()
    return build_user_query(db).filter(User.id == user.id).one()


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> User:
    """Администратор изменяет основные поля пользователя без удаления учетной записи."""
    user = build_user_query(db).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    data = payload.model_dump(exclude_unset=True)
    changes: dict = {}

    if "full_name" in data and data["full_name"] != user.full_name:
        changes["full_name"] = {"old": user.full_name, "new": data["full_name"]}
        user.full_name = data["full_name"]
    if "password" in data and data["password"] is not None:
        user.hashed_password = hash_password(data["password"])
        changes["password"] = "changed"
    if "role_code" in data and data["role_code"] is not None:
        role = get_role_by_code(db, data["role_code"])
        if role.id != user.role_id:
            changes["role"] = {"old": user.role.code, "new": role.code}
            user.role_id = role.id
    if "is_active" in data and data["is_active"] != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": data["is_active"]}
        user.is_active = data["is_active"]

    if changes:
        write_audit_log(db, actor_id=current_user.id, entity_type="user", entity_id=user.id, action="update_user", diff=changes)

    db.commit()
    return build_user_query(db).filter(User.id == user.id).one()
