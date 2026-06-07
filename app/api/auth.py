from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_roles
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def build_current_user_response(user: User) -> CurrentUserResponse:
    """Ответ собирается в одном месте, чтобы не повторять поля пользователя в каждом endpoint-е."""
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.code,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Вход выполняется по email и паролю, после успешной проверки возвращается JWT."""
    user = db.query(User).options(joinedload(User.role)).filter(User.email == payload.email).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    """Endpoint показывает пользователя, который определен по текущему Bearer-токену."""
    return build_current_user_response(current_user)


@router.get("/admin/ping", response_model=CurrentUserResponse)
def admin_ping(current_user: User = Depends(require_roles("admin"))) -> CurrentUserResponse:
    """Техническая проверка доступа только для администратора."""
    return build_current_user_response(current_user)


@router.get("/manager/ping", response_model=CurrentUserResponse)
def manager_ping(current_user: User = Depends(require_roles("admin", "manager"))) -> CurrentUserResponse:
    """Техническая проверка доступа для администратора и руководителя."""
    return build_current_user_response(current_user)


@router.get("/worker/ping", response_model=CurrentUserResponse)
def worker_ping(current_user: User = Depends(require_roles("admin", "manager", "worker"))) -> CurrentUserResponse:
    """Техническая проверка доступа для любой рабочей роли."""
    return build_current_user_response(current_user)
